package setup

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/fetch"
	"github.com/Fre0Grella/getsetmix/companion/internal/importer"
	"github.com/Fre0Grella/getsetmix/companion/internal/install"
	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/rekordbox"
)

// pcInfo is what Setup knows about this computer before asking anything.
type pcInfo struct {
	Name           string `json:"name"`
	Rekordbox      rbInfo `json:"rekordbox"`
	MusicDefault   string `json:"musicDefault"`
	LocalSupported bool   `json:"localSupported"` // a GetSetMix app build exists for this OS
	Paired         string `json:"paired,omitempty"`

	AppExe  string            `json:"-"`
	install rekordbox.Install // when Rekordbox.Found
}

type rbInfo struct {
	Found  bool   `json:"found"`
	Dir    string `json:"dir,omitempty"`
	Tracks int    `json:"tracks"`
	Folder string `json:"folder,omitempty"` // where most of the collection lives
}

func platform() string { return runtime.GOOS + "/" + runtime.GOARCH }

func detectPC(o Options) pcInfo {
	home, _ := os.UserHomeDir()
	info := pcInfo{
		MusicDefault:   filepath.Join(home, "Music", "GetSetMix"),
		LocalSupported: appAssets[platform()] != "",
	}
	info.Name, _ = os.Hostname()
	info.AppExe = filepath.Join(programsDir(o), "app", appFile())
	if o.Demo {
		info.Name = "STUDIO-PC"
		info.MusicDefault = `C:\Users\dj\Music\GetSetMix`
		info.Rekordbox = rbInfo{Found: true, Tracks: 1243, Folder: `C:\Users\dj\Music\Rekordbox`}
		info.LocalSupported = true
		return info
	}
	if inst, err := rekordbox.Locate("", ""); err == nil {
		info.install = inst
		info.Rekordbox = rbInfo{Found: true, Dir: inst.Dir}
		if db, err := library.OpenReadOnly(inst.DB()); err == nil {
			info.Rekordbox.Tracks, _ = db.TrackCount()
			info.Rekordbox.Folder, _ = db.DominantFolder()
			db.Close()
		}
	}
	if cfg, err := config.Load(o.Home); err == nil && cfg.Server != nil {
		info.Paired = cfg.Server.URL
	}
	return info
}

func appFile() string {
	if runtime.GOOS == "windows" {
		return "getsetmix.exe"
	}
	return "getsetmix"
}

// programsDir holds the companion and the local app. Under a sandboxed
// GSM_COMPANION_HOME it lives inside it, so tests touch nothing else.
func programsDir(o Options) string {
	if os.Getenv("GSM_COMPANION_HOME") != "" {
		return filepath.Join(o.Home, "programs")
	}
	if runtime.GOOS == "windows" {
		if d := os.Getenv("LOCALAPPDATA"); d != "" {
			return filepath.Join(d, "GetSetMix")
		}
	}
	return filepath.Join(o.Home, "Programs")
}

// appDataDir is where the local app keeps its settings: run_local.py's
// default for the packaged app.
func appDataDir(o Options) string {
	if os.Getenv("GSM_COMPANION_HOME") != "" {
		return filepath.Join(o.Home, "app-data")
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".getsetmix")
}

// pcChoice is what the person chose for this computer.
type pcChoice struct {
	Folder       string `json:"folder"`
	Delivery     string `json:"delivery"` // download | synced (server mode)
	Playlist     string `json:"playlist"`
	CopyExisting bool   `json:"copyExisting"`
}

var playlistSafe = regexp.MustCompile(`^[^\x00-\x1f/\\]{1,64}$`)

func (c *pcChoice) check() error {
	c.Folder = strings.TrimSpace(c.Folder)
	if c.Folder == "" || !filepath.IsAbs(c.Folder) {
		return errors.New("choose a folder for your tracks")
	}
	if c.Delivery == "" {
		c.Delivery = "download"
	}
	if c.Delivery != "download" && c.Delivery != "synced" {
		return fmt.Errorf("unknown delivery %q", c.Delivery)
	}
	if c.Playlist == "" {
		c.Playlist = config.DefaultPlaylist
	}
	if !playlistSafe.MatchString(c.Playlist) {
		return errors.New("the playlist name can't contain / or \\")
	}
	return nil
}

func pcSteps(mode string, c pcChoice) []Step {
	var ids []string
	if mode == "local" {
		ids = []string{"app", "ffmpeg", "deno", "settings", "shortcuts"}
	} else {
		ids = []string{"companion", "settings", "rekordbox"}
		if c.Delivery == "download" {
			ids = append(ids, "first")
		}
	}
	steps := make([]Step, len(ids))
	for i, id := range ids {
		steps[i] = Step{ID: id, Status: "pending"}
	}
	return steps
}

func (w *Wizard) handleLocalInstall(rw http.ResponseWriter, r *http.Request) {
	var c pcChoice
	if err := readJSON(r, &c); err != nil {
		fail(rw, 400, err.Error())
		return
	}
	c.Delivery = "download"
	if err := c.check(); err != nil {
		fail(rw, 400, err.Error())
		return
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	if !w.pc.LocalSupported {
		fail(rw, 400, "GetSetMix has no app for this computer yet: use a home server")
		return
	}
	if w.pcState == "running" {
		fail(rw, 409, "already installing")
		return
	}
	w.choice = c
	w.pcSteps = pcSteps("local", c)
	w.busy = true
	go w.runPC("local")
	writeJSON(rw, map[string]bool{"ok": true})
}

// runPC runs this computer's steps for mode ("local" or "server").
func (w *Wizard) runPC(mode string) {
	w.mu.Lock()
	if w.pcState == "running" || w.pcState == "done" {
		w.mu.Unlock()
		return
	}
	w.pcState = "running"
	steps := append([]Step(nil), w.pcSteps...)
	w.mu.Unlock()

	ctx := context.Background()
	for _, s := range steps {
		w.update(s.ID, "running", "", "", 0)
		var err error
		var note string
		if w.opts.Demo {
			err = w.demoStep(s.ID)
		} else {
			note, err = w.pcStep(ctx, mode, s.ID)
		}
		if err != nil {
			w.log.Printf("%s: %v", s.ID, err)
			w.update(s.ID, "fail", "", err.Error(), 0)
			w.mu.Lock()
			w.pcState, w.busy = "failed", false
			w.mu.Unlock()
			return
		}
		w.update(s.ID, "ok", "", note, 0)
	}
	w.mu.Lock()
	w.pcState, w.busy = "done", false
	w.mu.Unlock()
}

// update sets one of this computer's steps.
func (w *Wizard) update(id, status, code, detail string, progress float64) {
	w.mu.Lock()
	defer w.mu.Unlock()
	for i := range w.pcSteps {
		if w.pcSteps[i].ID == id {
			w.pcSteps[i] = Step{ID: id, Status: status, Code: code, Detail: detail, Progress: progress}
		}
	}
}

func (w *Wizard) progress(id string) func(float64) {
	return func(f float64) { w.update(id, "running", "", "", f) }
}

// pcStep does one step for real. It returns a note for the checklist.
func (w *Wizard) pcStep(ctx context.Context, mode, id string) (string, error) {
	w.mu.Lock()
	c, pc, srvURL, token := w.choice, w.pc, w.srvURL, w.token
	w.mu.Unlock()
	o := w.opts
	programs := programsDir(o)
	appDir := filepath.Join(programs, "app")
	bin := filepath.Join(appDir, "bin")

	switch id {
	case "app":
		return "", w.fetchApp(ctx, appDir)
	case "ffmpeg", "deno":
		for _, a := range tools[platform()][id] {
			if err := fetchAsset(ctx, a, bin, "", w.progress(id)); err != nil {
				return "", err
			}
		}
		return "", nil

	case "companion":
		_, err := w.placeCompanion(programs)
		return "", err

	case "settings":
		if err := os.MkdirAll(c.Folder, 0o755); err != nil {
			return "", err
		}
		cfg := config.Config{Folders: []string{c.Folder}, Playlist: c.Playlist}
		if o.DryRunOS {
			// A test run must never reach the real Rekordbox library.
			cfg.RekordboxDir = filepath.Join(o.Home, "no-rekordbox")
		}
		if mode == "server" && c.Delivery == "download" {
			cfg.Server = &fetch.Server{URL: srvURL, Token: token, Folder: c.Folder}
		}
		if mode == "local" {
			if err := writeAppSettings(appDataDir(o), c.Folder); err != nil {
				return "", err
			}
		}
		if err := os.MkdirAll(o.Home, 0o755); err != nil {
			return "", err
		}
		if err := cfg.Save(o.Home); err != nil {
			return "", err
		}
		var inst rekordbox.Install
		if pc.Rekordbox.Found {
			inst = pc.install
		}
		rep, err := importer.Baseline(o.Home, inst, cfg.Folders, false, time.Now())
		if err != nil {
			return "", err
		}
		if cfg.Server != nil {
			if err := w.seedFetchState(ctx, *cfg.Server, c.CopyExisting); err != nil {
				return "", err
			}
		}
		if rep.Files > 0 {
			return fmt.Sprintf("%d", rep.Files), nil
		}
		return "", nil

	case "rekordbox", "shortcuts":
		exe, err := w.placeCompanion(programs)
		if err != nil {
			return "", err
		}
		if o.DryRunOS {
			return "dry-run", nil
		}
		if id == "shortcuts" {
			icns := filepath.Join(filepath.Dir(o.Exe), "..", "Resources", "GetSetMix.icns")
			if _, err := install.InstallApp(pc.AppExe, icns); err != nil {
				return "", err
			}
		}
		_, err = install.Install(install.Options{
			Exe: exe, RekordboxExe: pc.install.Exe, Folders: []string{c.Folder},
			Fetch:        mode == "server" && c.Delivery == "download",
			SkipLauncher: !pc.Rekordbox.Found,
		})
		return "", err

	case "first":
		if o.DryRunOS {
			// Download in-process and stop there: no import, no Rekordbox.
			cfg, err := config.Load(o.Home)
			if err != nil {
				return "", err
			}
			state, err := fetch.LoadState(o.Home)
			if err != nil {
				return "", err
			}
			rep, err := (&fetch.Client{Server: *cfg.Server}).Run(ctx, state, time.Now)
			if serr := state.Save(o.Home); err == nil {
				err = serr
			}
			return fmt.Sprintf("%d", len(rep.Downloaded)), err
		}
		// Start the first download now, in the background: it may be long,
		// and the scheduled task would only run in a quarter of an hour.
		exe, err := w.placeCompanion(programs)
		if err != nil {
			return "", err
		}
		cmd := exec.Command(exe, "fetch")
		hideWindow(cmd)
		if err := cmd.Start(); err != nil {
			return "", err
		}
		go cmd.Wait()
		return "", nil
	}
	return "", fmt.Errorf("unknown step %q", id)
}

// placeCompanion copies this program into the programs folder, where the
// launcher and the scheduled task find it. Windows gets the windowless
// name, which the launcher prefers.
func (w *Wizard) placeCompanion(programs string) (string, error) {
	name := "gsm-companion"
	if runtime.GOOS == "windows" {
		name = "gsm-companionw.exe"
	}
	dst := filepath.Join(programs, name)
	if same(w.opts.Exe, dst) {
		return dst, nil
	}
	if err := os.MkdirAll(programs, 0o755); err != nil {
		return "", err
	}
	in, err := os.Open(w.opts.Exe)
	if err != nil {
		return "", err
	}
	defer in.Close()
	tmp := dst + ".new"
	out, err := os.OpenFile(tmp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o755)
	if err != nil {
		return "", err
	}
	_, err = io.Copy(out, in)
	if cerr := out.Close(); err == nil {
		err = cerr
	}
	if err != nil {
		os.Remove(tmp)
		return "", err
	}
	return dst, replace(tmp, dst)
}

func same(a, b string) bool {
	ia, err1 := os.Stat(a)
	ib, err2 := os.Stat(b)
	return err1 == nil && err2 == nil && os.SameFile(ia, ib)
}

// seedFetchState decides what the first fetch downloads: everything the
// server has, or (copyExisting false) only what arrives from now on.
func (w *Wizard) seedFetchState(ctx context.Context, srv fetch.Server, copyExisting bool) error {
	state := &fetch.State{Fetched: map[string]time.Time{}}
	if !copyExisting {
		ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
		defer cancel()
		l, err := (&fetch.Client{Server: srv}).List(ctx)
		if err != nil {
			return err
		}
		now := time.Now()
		for _, f := range l.Files {
			state.Fetched[f.Path] = now
		}
	}
	return state.Save(w.opts.Home)
}

// fetchApp downloads the GetSetMix app for this platform: from the release
// matching Setup's version, or the latest; AppURL overrides it (a URL or a
// local file, for testing a build).
func (w *Wizard) fetchApp(ctx context.Context, dir string) error {
	src := w.opts.AppURL
	if src == "" {
		name := appAssets[platform()]
		if semver.MatchString(w.opts.Version) {
			src = fmt.Sprintf("https://github.com/Fre0Grella/getsetmix/releases/download/v%s/%s", w.opts.Version, name)
		} else {
			src = "https://github.com/Fre0Grella/getsetmix/releases/latest/download/" + name
		}
	}
	if !strings.Contains(src, "://") {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return err
		}
		in, err := os.Open(src)
		if err != nil {
			return err
		}
		defer in.Close()
		tmp := filepath.Join(dir, ".app.part")
		out, err := os.OpenFile(tmp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o755)
		if err != nil {
			return err
		}
		_, err = io.Copy(out, in)
		if cerr := out.Close(); err == nil {
			err = cerr
		}
		if err != nil {
			return err
		}
		return replace(tmp, filepath.Join(dir, appFile()))
	}
	return fetchAsset(ctx, asset{URL: src}, dir, appFile(), w.progress("app"))
}

var semver = regexp.MustCompile(`^\d+\.\d+\.\d+$`)

// writeAppSettings points the local app's library at folder, keeping any
// other settings it has.
func writeAppSettings(dir, folder string) error {
	path := filepath.Join(dir, "config.json")
	settings := map[string]any{}
	if data, err := os.ReadFile(path); err == nil {
		_ = json.Unmarshal(data, &settings)
	}
	settings["library_root"] = folder
	data, err := json.MarshalIndent(settings, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, append(data, '\n'), 0o644)
}

// launchApp starts the local app's window. The app's console stays hidden:
// closing the window ends it.
func launchApp(exe string) error {
	cmd := exec.Command(exe, "--window")
	hideWindow(cmd)
	return cmd.Start()
}
