// gsm-companion imports the tracks GetSetMix delivers straight into the
// Rekordbox collection on the DJ's computer — no XML to refresh, no drag and
// drop. See companion/README.md.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/fetch"
	"github.com/Fre0Grella/getsetmix/companion/internal/importer"
	"github.com/Fre0Grella/getsetmix/companion/internal/install"
	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/rekordbox"
	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
	"github.com/Fre0Grella/getsetmix/companion/internal/setup"
	"github.com/Fre0Grella/getsetmix/companion/internal/watch"
)

// version is set at build time: -ldflags "-X main.version=1.2.3".
var version = "dev"

const usage = `gsm-companion %s — imports GetSetMix downloads into Rekordbox

Usage:
  gsm-companion                         open GetSetMix Setup (also: wizard [--demo])
  gsm-companion setup [--folder DIR]... [--playlist NAME] [--import-existing]
  gsm-companion install [--autostart]   create the "Rekordbox (GetSetMix)" launcher
  gsm-companion launch                  import new tracks, then start Rekordbox
  gsm-companion sync [--dry-run] [--wait]
  gsm-companion fetch [--for DURATION]  download new tracks from the server, then import
  gsm-companion watch                   stay running, import as tracks arrive
  gsm-companion status
  gsm-companion uninstall
  gsm-companion version

Rekordbox has to be closed while tracks are written to its collection, so
"launch" (used by the launcher) imports first and then starts Rekordbox.
Nothing keeps running afterwards.
`

func main() {
	// Double-clicked (or opened from Finder, which may add -psn_…): this is
	// GetSetMix Setup.
	if len(os.Args) < 2 || strings.HasPrefix(os.Args[1], "-psn_") {
		os.Args = []string{os.Args[0], "wizard"}
	}
	cmd, args := os.Args[1], os.Args[2:]
	home, err := config.Dir()
	if err != nil {
		fatal(err)
	}
	logger, closeLog := openLog(home)
	defer closeLog()

	switch cmd {
	case "wizard":
		err = cmdWizard(home, logger, args)
	case "setup":
		err = cmdSetup(home, args)
	case "install":
		err = cmdInstall(home, args)
	case "uninstall":
		err = cmdUninstall()
	case "launch":
		err = cmdLaunch(home, logger)
	case "sync":
		err = cmdSync(home, logger, args)
	case "fetch":
		err = cmdFetch(home, logger, args)
	case "watch":
		err = cmdWatch(home, logger)
	case "status":
		err = cmdStatus(home)
	case "version", "--version", "-v":
		fmt.Println(version)
	case "help", "--help", "-h":
		fmt.Printf(usage, version)
	default:
		fmt.Fprintf(os.Stderr, usage, version)
		os.Exit(2)
	}
	if err != nil {
		logger.Printf("%s: %v", cmd, err)
		fatal(err)
	}
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "gsm-companion:", err)
	os.Exit(1)
}

// openLog appends to companion.log in the companion folder (and mirrors to
// stdout when there is a console). The file is trimmed when it passes 1 MB.
func openLog(home string) (*log.Logger, func()) {
	_ = os.MkdirAll(home, 0o755)
	path := filepath.Join(home, "companion.log")
	if info, err := os.Stat(path); err == nil && info.Size() > 1<<20 {
		_ = os.Rename(path, path+".1")
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return log.New(os.Stdout, "", log.LstdFlags), func() {}
	}
	// File first: writes to a missing console fail, and MultiWriter stops there.
	return log.New(io.MultiWriter(f, os.Stdout), "", log.LstdFlags), func() { f.Close() }
}

func load(home string) (config.Config, rekordbox.Install, error) {
	cfg, err := config.Load(home)
	if err != nil {
		return cfg, rekordbox.Install{}, err
	}
	inst, err := rekordbox.Locate(cfg.RekordboxDir, cfg.RekordboxExe)
	return cfg, inst, err
}

func newImporter(home string, logger *log.Logger) (*importer.Importer, error) {
	cfg, inst, err := load(home)
	if err != nil {
		return nil, err
	}
	return &importer.Importer{
		Install: inst, Config: cfg, Home: home, Log: logger,
		Now: time.Now, IsRunning: rekordbox.IsRunning,
	}, nil
}

// ------------------------------------------------------------------ setup

type multiFlag []string

func (m *multiFlag) String() string     { return strings.Join(*m, ", ") }
func (m *multiFlag) Set(v string) error { *m = append(*m, v); return nil }

func cmdSetup(home string, args []string) error {
	fs := flag.NewFlagSet("setup", flag.ExitOnError)
	var folders multiFlag
	fs.Var(&folders, "folder", "folder to watch (repeatable); default: where most of your collection lives")
	playlist := fs.String("playlist", config.DefaultPlaylist, "playlist new tracks are added to")
	importExisting := fs.Bool("import-existing", false,
		"also import tracks already in the folder that Rekordbox doesn't have")
	rbDir := fs.String("rekordbox-dir", "", "folder holding master.db (auto-detected)")
	_ = fs.Parse(args)

	inst, err := rekordbox.Locate(*rbDir, "")
	if err != nil {
		return err
	}
	db, err := library.OpenReadOnly(inst.DB())
	if err != nil {
		return err
	}
	defer db.Close()
	if len(folders) == 0 {
		dir, err := db.DominantFolder()
		if err != nil {
			return fmt.Errorf("pass --folder: %w", err)
		}
		folders = append(folders, dir)
		fmt.Printf("Watching %s (where most of your collection lives; use --folder to change)\n", dir)
	}
	for i, f := range folders {
		abs, err := filepath.Abs(f)
		if err != nil {
			return err
		}
		if info, err := os.Stat(abs); err != nil || !info.IsDir() {
			return fmt.Errorf("%s is not a folder", abs)
		}
		folders[i] = abs
	}
	cfg := config.Config{Folders: folders, Playlist: *playlist, RekordboxDir: *rbDir}
	if err := cfg.Save(home); err != nil {
		return err
	}

	// Baseline: what is already there is "handled", so only tracks that
	// arrive from now on are imported (unless --import-existing).
	db.Close()
	rep, err := importer.Baseline(home, inst, folders, *importExisting, time.Now())
	if err != nil {
		return err
	}
	inCollection, outside := rep.InCollection, rep.Outside
	fmt.Printf("Rekordbox library: %s\n", inst.Dir)
	fmt.Printf("%d track(s) in the folder, %d already in Rekordbox.\n", rep.Files, inCollection)
	if outside > 0 {
		if *importExisting {
			fmt.Printf("%d track(s) Rekordbox doesn't have will be imported on the next sync.\n", outside)
		} else {
			fmt.Printf("%d track(s) Rekordbox doesn't have were left alone "+
				"(re-run with --import-existing to import them).\n", outside)
		}
	}
	fmt.Printf("New tracks will be added to the %q playlist.\n\nNext: gsm-companion install\n", cfg.Playlist)
	return nil
}

// ----------------------------------------------------------------- wizard

func cmdWizard(home string, logger *log.Logger, args []string) error {
	fs := flag.NewFlagSet("wizard", flag.ExitOnError)
	demo := fs.Bool("demo", false, "play the whole flow with a pretend server; change nothing")
	noWindow := fs.Bool("no-window", false, "print the address instead of opening a window")
	dryRunOS := fs.Bool("dry-run-os", false, "skip shortcuts, scheduled tasks and autostart")
	image := fs.String("image", os.Getenv("GSM_SETUP_IMAGE"), "server image to install (default: the published one)")
	app := fs.String("app", os.Getenv("GSM_SETUP_APP"), "GetSetMix app to install on this computer (URL or file)")
	port := fs.Int("pair-port", 0, "network port the server calls back on (default 47321)")
	_ = fs.Parse(args)
	exe, err := install.Self()
	if err != nil {
		return err
	}
	return setup.Run(context.Background(), setup.Options{
		Version: version, Home: home, Exe: exe, Demo: *demo, NoWindow: *noWindow, DryRunOS: *dryRunOS,
		Image: *image, AppURL: *app, PairPort: *port, Log: logger,
	})
}

// ---------------------------------------------------------------- install

func cmdInstall(home string, args []string) error {
	fs := flag.NewFlagSet("install", flag.ExitOnError)
	autostart := fs.Bool("autostart", false, "also import unattended, without using the launcher")
	_ = fs.Parse(args)
	cfg, inst, err := load(home)
	if err != nil {
		return err
	}
	exe, err := install.Self()
	if err != nil {
		return err
	}
	res, err := install.Install(install.Options{
		Exe: exe, RekordboxExe: inst.Exe, Folders: cfg.Folders, Autostart: *autostart,
	})
	for _, c := range res.Created {
		fmt.Println("created", c)
	}
	for _, n := range res.Notes {
		fmt.Println("note:", n)
	}
	if err == nil {
		fmt.Printf("\nOpen Rekordbox with %q from now on: it imports new tracks first.\n", install.LauncherName)
	}
	return err
}

func cmdUninstall() error {
	res, err := install.Uninstall()
	for _, c := range res.Created {
		fmt.Println("removed", c)
	}
	return err
}

// ------------------------------------------------------------ the work

// cmdLaunch never stands between the DJ and Rekordbox: whatever happens to
// the import, Rekordbox starts.
func cmdLaunch(home string, logger *log.Logger) error {
	cfg, _ := config.Load(home)
	inst, _ := rekordbox.Locate(cfg.RekordboxDir, cfg.RekordboxExe)
	if cfg.Server != nil {
		// Whatever arrived since the last scheduled fetch, within a budget
		// short enough not to make anyone wait for Rekordbox.
		if _, err := runFetch(home, cfg, logger, 20*time.Second); err != nil {
			logger.Printf("launch: fetch: %v", err)
		}
	}
	if running, _ := rekordbox.IsRunning(); !running {
		if im, err := newImporter(home, logger); err != nil {
			logger.Printf("launch: import skipped: %v", err)
		} else if rep, err := im.Sync(false); err != nil {
			logger.Printf("launch: import failed: %v", err)
		} else if len(rep.Imported) > 0 {
			logger.Printf("launch: imported %d track(s) into %q", len(rep.Imported), cfg.Playlist)
		}
	}
	if inst.Exe == "" {
		return errors.New("Rekordbox not found; set rekordbox_exe in companion.json")
	}
	return rekordbox.Launch(inst.Exe)
}

func cmdSync(home string, logger *log.Logger, args []string) error {
	fs := flag.NewFlagSet("sync", flag.ExitOnError)
	dryRun := fs.Bool("dry-run", false, "show what would be imported; change nothing")
	wait := fs.Bool("wait", false, "if Rekordbox is open, wait for it to close, then import")
	_ = fs.Parse(args)
	im, err := newImporter(home, logger)
	if err != nil {
		return err
	}
	rep, err := im.Sync(*dryRun)
	if errors.Is(err, importer.ErrRekordboxRunning) && *wait {
		logger.Printf("%d new track(s): waiting for Rekordbox to close", rep.New)
		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
		defer stop()
		if err := rekordbox.WaitClosed(ctx); err != nil {
			return err
		}
		rep, err = im.Sync(false)
	}
	printReport(rep)
	return err
}

// cmdFetch downloads new tracks from the server and imports them when
// Rekordbox is closed; when it is open they wait for the launcher or the next
// fetch. The scheduled task runs this every few minutes.
func cmdFetch(home string, logger *log.Logger, args []string) error {
	fs := flag.NewFlagSet("fetch", flag.ExitOnError)
	budget := fs.Duration("for", 30*time.Minute, "stop downloading after this long")
	_ = fs.Parse(args)
	cfg, err := config.Load(home)
	if err != nil {
		return err
	}
	if cfg.Server == nil {
		return errors.New("no server paired: run GetSetMix Setup")
	}
	rep, err := runFetch(home, cfg, logger, *budget)
	if err != nil {
		return err
	}
	if len(rep.Downloaded) == 0 {
		return nil
	}
	im, err := newImporter(home, logger)
	if errors.Is(err, rekordbox.ErrNotFound) {
		// Downloading still keeps this computer's copy; importing waits for
		// Rekordbox to be installed (and Setup to be run again).
		logger.Printf("fetch: Rekordbox not found here; %d track(s) downloaded, not imported", len(rep.Downloaded))
		return nil
	}
	if err != nil {
		return err
	}
	irep, err := im.Sync(false)
	if errors.Is(err, importer.ErrRekordboxRunning) {
		logger.Printf("fetch: %d track(s) wait for Rekordbox to close", irep.New)
		return nil
	}
	if err == nil && len(irep.Imported) > 0 {
		logger.Printf("fetch: imported %d track(s) into %q", len(irep.Imported), cfg.Playlist)
	}
	return err
}

// runFetch is one fetch, guarded so the launcher and the scheduled task
// never download at the same time.
func runFetch(home string, cfg config.Config, logger *log.Logger, budget time.Duration) (fetch.Report, error) {
	unlock, err := lock(home, "fetch")
	if err != nil {
		return fetch.Report{}, err
	}
	defer unlock()
	state, err := fetch.LoadState(home)
	if err != nil {
		return fetch.Report{}, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), budget)
	defer cancel()
	c := &fetch.Client{Server: *cfg.Server}
	rep, err := c.Run(ctx, state, time.Now)
	if serr := state.Save(home); err == nil {
		err = serr
	}
	for _, p := range rep.Downloaded {
		logger.Printf("fetched %s", p)
	}
	for p, why := range rep.Failed {
		logger.Printf("fetch failed %s: %s", p, why)
	}
	if rep.Remaining > 0 {
		logger.Printf("fetch: %d track(s) left for next time", rep.Remaining)
	}
	return rep, err
}

// lock takes a lock file, stealing it when its holder is clearly gone.
func lock(home, name string) (func(), error) {
	path := filepath.Join(home, name+".lock")
	for i := 0; i < 2; i++ {
		f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
		if err == nil {
			f.Close()
			return func() { os.Remove(path) }, nil
		}
		if info, serr := os.Stat(path); serr == nil && time.Since(info.ModTime()) > 2*time.Hour {
			os.Remove(path)
			continue
		}
		break
	}
	return nil, fmt.Errorf("another %s is running", name)
}

func cmdWatch(home string, logger *log.Logger) error {
	im, err := newImporter(home, logger)
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	logger.Printf("watching %s", strings.Join(im.Config.Folders, ", "))
	return watch.Run(ctx, im)
}

func cmdStatus(home string) error {
	cfg, inst, err := load(home)
	if err != nil {
		return err
	}
	fmt.Printf("version     %s\n", version)
	fmt.Printf("watching    %s\n", strings.Join(cfg.Folders, ", "))
	fmt.Printf("playlist    %s\n", cfg.Playlist)
	if cfg.Server != nil {
		fmt.Printf("server      %s -> %s\n", cfg.Server.URL, cfg.Server.Folder)
	}
	fmt.Printf("rekordbox   %s\n", inst.Dir)
	if inst.Exe != "" {
		fmt.Printf("program     %s\n", inst.Exe)
	}
	running, _ := rekordbox.IsRunning()
	fmt.Printf("running     %v\n", running)
	if db, err := library.OpenReadOnly(inst.DB()); err == nil {
		n, _ := db.TrackCount()
		db.Close()
		fmt.Printf("collection  %d tracks\n", n)
	} else {
		fmt.Printf("collection  unreadable: %v\n", err)
	}
	state, err := config.LoadState(home)
	if err != nil {
		return err
	}
	found, err := scan.Folders(cfg.Folders, time.Now())
	if err != nil {
		return err
	}
	pending := 0
	for _, f := range found.Ready {
		if _, ok := state.Seen[f.Key]; !ok {
			pending++
		}
	}
	fmt.Printf("pending     %d new, %d still syncing\n", pending, len(found.Settling))
	fmt.Printf("log         %s\n", filepath.Join(home, "companion.log"))
	return nil
}

func printReport(rep importer.Report) {
	verb := "imported"
	if rep.DryRun {
		verb = "would import"
	}
	for _, p := range rep.Imported {
		fmt.Printf("%s  %s\n", verb, filepath.Base(p))
	}
	for p, why := range rep.Failed {
		fmt.Printf("failed       %s: %s\n", filepath.Base(p), why)
	}
	fmt.Printf("%d new, %d %s, %d already in Rekordbox, %d failed, %d still syncing\n",
		rep.New, len(rep.Imported), verb, len(rep.Already), len(rep.Failed), rep.Settling)
}
