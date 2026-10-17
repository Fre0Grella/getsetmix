// Package setup is GetSetMix Setup: the window that installs GetSetMix.
//
// It asks one question first: everything on this computer, or with a home
// server. "This computer" downloads the app, ffmpeg and Deno and creates a
// GetSetMix shortcut. "Home server" shows one command to paste on the server
// (see serverscript), installs or adopts GetSetMix there with automatic
// updates, and pairs this computer so new tracks download here on their own.
// Both end by wiring the companion into Rekordbox.
//
// The window is a local web page (127.0.0.1, behind a per-run key) shown in
// a browser's app mode; a second listener on the network answers only the
// server's paired requests.
package setup

import (
	"context"
	"crypto/rand"
	"embed"
	"encoding/base32"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/serverscript"
)

//go:embed ui
var uiFiles embed.FS

// Options configure a run.
type Options struct {
	Version string
	Home    string // companion folder (config.Dir())
	// Exe is this program: copied into place as the companion.
	Exe string
	// Demo fakes the server and every side effect: for screenshots and
	// trying the flow. Nothing is written anywhere.
	Demo bool
	// DryRunOS does everything except touch the desktop: no shortcuts,
	// scheduled tasks or autostart (for end-to-end tests on a real machine).
	DryRunOS bool
	// NoWindow prints the address instead of opening a window.
	NoWindow bool
	// Image overrides the server image (testing a local build).
	Image string
	// AppURL overrides where "This computer" gets the GetSetMix app from
	// (a URL or a local file).
	AppURL string
	// PairPort is the network port the server calls back on.
	PairPort int
	Log      *log.Logger
}

// Step is one line of a progress checklist.
type Step struct {
	ID       string  `json:"id"`
	Status   string  `json:"status"` // pending running ok warn fail
	Code     string  `json:"code,omitempty"`
	Detail   string  `json:"detail,omitempty"`
	Progress float64 `json:"progress,omitempty"`
}

// Wizard is one run of Setup.
type Wizard struct {
	opts Options
	log  *log.Logger
	key  string // the UI's session key

	mu       sync.Mutex
	lastSeen time.Time
	busy     bool // an installation is running: don't quit on a quiet page

	// pairing
	code     string
	pairSrv  *http.Server
	pairPort int
	pcIPs    []string
	facts    *serverscript.Facts
	srvBase  string // the address the server reached Setup at
	plan     *serverscript.Plan
	script   string
	planCh   chan struct{} // closed when script is ready (or cancelled)
	cancel   bool
	token    string
	label    string
	srvSteps []Step
	srvState string // "", running, done, failed
	srvPort  int
	srvURL   string
	urlState string // "", checking, ok, need
	urlError string
	srvFiles int

	// this computer
	pc      pcInfo
	pcSteps []Step
	pcState string // "", running, done, failed
	choice  pcChoice
}

// Run shows Setup until its window closes.
func Run(ctx context.Context, opts Options) error {
	if opts.Log == nil {
		opts.Log = log.New(os.Stderr, "setup: ", log.LstdFlags)
	}
	if opts.PairPort == 0 {
		opts.PairPort = 47321
	}
	w := &Wizard{opts: opts, log: opts.Log, key: randomKey(18), lastSeen: time.Now(),
		code: randomCode(), planCh: make(chan struct{})}
	w.token = randomKey(32)
	w.label, _ = os.Hostname()
	w.pc = detectPC(opts)

	ctx, stop := context.WithCancel(ctx)
	defer stop()

	ui, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return err
	}
	uiSrv := &http.Server{Handler: w.uiHandler(), ReadHeaderTimeout: 10 * time.Second}
	go uiSrv.Serve(ui)
	defer uiSrv.Close()

	defer w.stopPair()

	url := fmt.Sprintf("http://%s/?k=%s", ui.Addr(), w.key)
	var closed <-chan struct{}
	if opts.NoWindow {
		fmt.Println("GetSetMix Setup is at", url)
	} else {
		profile := filepath.Join(os.TempDir(), "getsetmix-setup-window")
		if closed, err = appWindow(ctx, url, profile, 1000, 740); err != nil {
			return err
		}
	}

	tick := time.NewTicker(5 * time.Second)
	defer tick.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-closed:
			w.finish()
			return nil
		case <-tick.C:
			// Without an app window, a page that stopped asking for news is
			// a closed tab.
			w.mu.Lock()
			gone := closed == nil && !opts.NoWindow && !w.busy && time.Since(w.lastSeen) > 90*time.Second
			w.mu.Unlock()
			if gone {
				w.finish()
				return nil
			}
		}
	}
}

// finish tells a server still waiting for choices that Setup is gone.
func (w *Wizard) finish() {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.script == "" && !w.cancel {
		w.cancel = true
		close(w.planCh)
	}
}

// startPair opens the listener the server calls back on. Only "With my home
// server" needs it, so it waits until then: opening a network port is what
// makes Windows ask about the firewall.
func (w *Wizard) startPair() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.pairSrv != nil {
		return nil
	}
	ln, err := listenPair(w.opts.PairPort)
	if err != nil {
		return err
	}
	w.pairPort = ln.Addr().(*net.TCPAddr).Port
	w.pcIPs = lanIPs()
	w.pairSrv = &http.Server{Handler: w.pairHandler(), ReadHeaderTimeout: 10 * time.Second}
	go w.pairSrv.Serve(ln)
	return nil
}

func (w *Wizard) stopPair() {
	w.mu.Lock()
	srv := w.pairSrv
	w.mu.Unlock()
	if srv != nil {
		srv.Close()
	}
}

func (w *Wizard) handlePairStart(rw http.ResponseWriter, r *http.Request) {
	if err := w.startPair(); err != nil {
		fail(rw, 500, err.Error())
		return
	}
	writeJSON(rw, map[string]bool{"ok": true})
}

func listenPair(port int) (net.Listener, error) {
	ln, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil { // a second Setup, or the port is taken: any port will do
		ln, err = net.Listen("tcp", ":0")
	}
	return ln, err
}

// ---------------------------------------------------------------- the UI

func (w *Wizard) uiHandler() http.Handler {
	static, _ := fs.Sub(uiFiles, "ui")
	files := http.FileServer(http.FS(static))
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/state", w.handleState)
	mux.HandleFunc("POST /api/pick", w.handlePick)
	mux.HandleFunc("POST /api/pair/start", w.handlePairStart)
	mux.HandleFunc("POST /api/server/install", w.handleServerInstall)
	mux.HandleFunc("POST /api/server/url", w.handleServerURL)
	mux.HandleFunc("POST /api/server/cancel", w.handleServerCancel)
	mux.HandleFunc("POST /api/local/install", w.handleLocalInstall)
	mux.HandleFunc("POST /api/open", w.handleOpen)
	mux.HandleFunc("GET /api/qr", w.handleQR)
	mux.HandleFunc("GET /api/script", w.handleScriptPreview)
	if w.opts.Demo {
		mux.HandleFunc("POST /api/demo/connect", w.handleDemoConnect)
	}
	mux.Handle("/", files)

	return http.HandlerFunc(func(rw http.ResponseWriter, r *http.Request) {
		// Only this run's page may drive Setup: the key arrives once in the
		// URL and lives on as a cookie; the Host check stops DNS rebinding.
		if h, _, _ := net.SplitHostPort(r.Host); h != "127.0.0.1" {
			http.Error(rw, "forbidden", http.StatusForbidden)
			return
		}
		if k := r.URL.Query().Get("k"); k == w.key {
			http.SetCookie(rw, &http.Cookie{Name: "gsm_setup", Value: w.key, Path: "/", HttpOnly: true, SameSite: http.SameSiteStrictMode})
			http.Redirect(rw, r, "/", http.StatusSeeOther)
			return
		}
		if c, err := r.Cookie("gsm_setup"); err != nil || c.Value != w.key {
			http.Error(rw, "Open GetSetMix Setup again: this page belongs to a previous run.", http.StatusForbidden)
			return
		}
		if r.Method == http.MethodPost && r.Header.Get("Content-Type") != "application/json" {
			http.Error(rw, "json only", http.StatusUnsupportedMediaType)
			return
		}
		rw.Header().Set("Cache-Control", "no-store")
		mux.ServeHTTP(rw, r)
	})
}

func writeJSON(rw http.ResponseWriter, v any) {
	rw.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(rw).Encode(v)
}

func readJSON(r *http.Request, v any) error {
	return json.NewDecoder(http.MaxBytesReader(nil, r.Body, 1<<16)).Decode(v)
}

func fail(rw http.ResponseWriter, status int, msg string) {
	rw.Header().Set("Content-Type", "application/json")
	rw.WriteHeader(status)
	_ = json.NewEncoder(rw).Encode(map[string]string{"error": msg})
}

type stateView struct {
	Version string  `json:"version"`
	OS      string  `json:"os"`
	Demo    bool    `json:"demo"`
	PC      pcInfo  `json:"pc"`
	Pair    pairV   `json:"pair"`
	Server  serverV `json:"server"`
	Local   localV  `json:"local"`
}

type pairV struct {
	Command   string     `json:"command"`
	Commands  []cmdV     `json:"commands"`
	Connected bool       `json:"connected"`
	Facts     *factsView `json:"facts,omitempty"`
}

type cmdV struct {
	IP      string `json:"ip"`
	Command string `json:"command"`
	Kind    string `json:"kind"` // lan | tailscale | other
}

type serverV struct {
	State    string   `json:"state"`
	Steps    []Step   `json:"steps"`
	URL      string   `json:"url"`
	URLState string   `json:"urlState"`
	URLError string   `json:"urlError,omitempty"`
	HTTPS    bool     `json:"https"`
	Files    int      `json:"files"`
	Plan     *planV   `json:"plan,omitempty"`
	Hints    []string `json:"hints,omitempty"`
}

type localV struct {
	State string `json:"state"`
	Steps []Step `json:"steps"`
}

func (w *Wizard) handleState(rw http.ResponseWriter, r *http.Request) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.lastSeen = time.Now()
	v := stateView{Version: w.opts.Version, OS: runtime.GOOS, Demo: w.opts.Demo, PC: w.pc}
	for _, ip := range w.pcIPs {
		kind := "lan"
		if strings.HasPrefix(ip, "100.") {
			kind = "tailscale"
		}
		v.Pair.Commands = append(v.Pair.Commands, cmdV{IP: ip, Command: w.command(ip), Kind: kind})
	}
	if len(v.Pair.Commands) > 0 {
		v.Pair.Command = v.Pair.Commands[0].Command
	}
	if w.facts != nil {
		v.Pair.Connected = true
		v.Pair.Facts = viewFacts(*w.facts)
	}
	v.Server = serverV{State: w.srvState, Steps: w.srvSteps, URL: w.srvURL, URLState: w.urlState,
		URLError: w.urlError, Files: w.srvFiles, HTTPS: strings.HasPrefix(w.srvURL, "https://")}
	if w.plan != nil {
		v.Server.Plan = viewPlan(*w.plan)
	}
	v.Local = localV{State: w.pcState, Steps: w.pcSteps}
	writeJSON(rw, v)
}

func (w *Wizard) command(ip string) string {
	return fmt.Sprintf("curl -fsSL http://%s/s/%s | sudo sh", net.JoinHostPort(ip, fmt.Sprint(w.pairPort)), w.code)
}

func (w *Wizard) handlePick(rw http.ResponseWriter, r *http.Request) {
	var req struct{ Prompt, Start string }
	if err := readJSON(r, &req); err != nil {
		fail(rw, 400, err.Error())
		return
	}
	if w.opts.Demo {
		writeJSON(rw, map[string]string{"path": req.Start})
		return
	}
	path, err := pickFolder(req.Prompt, req.Start)
	if errors.Is(err, errCancelled) {
		writeJSON(rw, map[string]string{})
		return
	}
	if err != nil {
		fail(rw, 500, err.Error())
		return
	}
	writeJSON(rw, map[string]string{"path": path})
}

func (w *Wizard) handleOpen(rw http.ResponseWriter, r *http.Request) {
	var req struct{ What string }
	if err := readJSON(r, &req); err != nil {
		fail(rw, 400, err.Error())
		return
	}
	w.mu.Lock()
	url, folder, app := w.srvURL, w.choice.Folder, w.pc.AppExe
	w.mu.Unlock()
	if w.opts.Demo {
		writeJSON(rw, map[string]bool{"ok": true})
		return
	}
	var err error
	switch req.What {
	case "server":
		err = openURL(url)
	case "folder":
		err = openPath(folder)
	case "app":
		err = launchApp(app)
	case "tailscale":
		err = openURL("https://tailscale.com/download")
	case "tailscale-https":
		err = openURL("https://login.tailscale.com/admin/dns")
	default:
		err = fmt.Errorf("can't open %q", req.What)
	}
	if err != nil {
		fail(rw, 500, err.Error())
		return
	}
	writeJSON(rw, map[string]bool{"ok": true})
}

// ------------------------------------------------------------- helpers

func randomKey(n int) string {
	b := make([]byte, n)
	_, _ = rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}

// randomCode is short enough to read aloud, long enough not to guess
// during one Setup (40 bits; the listener goes away with the window).
func randomCode() string {
	b := make([]byte, 5)
	_, _ = rand.Read(b)
	return strings.ToLower(base32.NewEncoding("ABCDEFGHJKMNPQRSTUVWXYZ023456789").WithPadding(base32.NoPadding).EncodeToString(b))
}

// lanIPs are this computer's addresses a server could reach, most likely
// first: home-network addresses, then Tailscale.
func lanIPs() []string {
	var lan, ts []string
	ifaces, _ := net.Interfaces()
	for _, ifc := range ifaces {
		if ifc.Flags&net.FlagUp == 0 || ifc.Flags&net.FlagLoopback != 0 {
			continue
		}
		name := strings.ToLower(ifc.Name)
		if strings.Contains(name, "vethernet") || strings.Contains(name, "virtualbox") ||
			strings.Contains(name, "vmware") || strings.HasPrefix(name, "docker") ||
			strings.HasPrefix(name, "br-") || strings.HasPrefix(name, "veth") {
			continue
		}
		addrs, _ := ifc.Addrs()
		for _, a := range addrs {
			ipn, ok := a.(*net.IPNet)
			if !ok || ipn.IP.To4() == nil || ipn.IP.IsLinkLocalUnicast() {
				continue
			}
			ip := ipn.IP.To4()
			switch {
			case ip[0] == 100 && ip[1] >= 64 && ip[1] < 128: // CGNAT: Tailscale
				ts = append(ts, ip.String())
			case ip.IsPrivate():
				lan = append(lan, ip.String())
			}
		}
	}
	return append(lan, ts...)
}
