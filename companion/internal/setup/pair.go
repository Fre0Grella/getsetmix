package setup

import (
	"context"
	"crypto/subtle"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"rsc.io/qr"

	"github.com/Fre0Grella/getsetmix/companion/internal/fetch"
	"github.com/Fre0Grella/getsetmix/companion/internal/serverscript"
)

// pairHandler answers the server, and nothing else, on the network.
func (w *Wizard) pairHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /s/{code}", w.handleBootstrap)
	mux.HandleFunc("POST /s/{code}/facts", w.handleFacts)
	mux.HandleFunc("GET /s/{code}/plan", w.handlePlan)
	mux.HandleFunc("POST /s/{code}/log", w.handleLog)
	return http.HandlerFunc(func(rw http.ResponseWriter, r *http.Request) {
		code := strings.TrimPrefix(r.URL.Path, "/s/")
		code, _, _ = strings.Cut(code, "/")
		if subtle.ConstantTimeCompare([]byte(code), []byte(w.code)) != 1 {
			time.Sleep(time.Second) // make guessing slow
			http.NotFound(rw, r)
			return
		}
		mux.ServeHTTP(rw, r)
	})
}

func (w *Wizard) base(r *http.Request) string {
	return "http://" + r.Host + "/s/" + w.code
}

func (w *Wizard) handleBootstrap(rw http.ResponseWriter, r *http.Request) {
	rw.Header().Set("Content-Type", "text/plain; charset=utf-8")
	io.WriteString(rw, serverscript.Bootstrap(w.base(r)))
}

func (w *Wizard) handleFacts(rw http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(http.MaxBytesReader(rw, r.Body, 1<<20))
	if err != nil {
		http.Error(rw, err.Error(), http.StatusBadRequest)
		return
	}
	f := serverscript.ParseFacts(string(body))
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.srvState == "running" {
		http.Error(rw, "an installation is already running", http.StatusConflict)
		return
	}
	// The command was run again (or on another server): start over.
	w.facts = &f
	w.srvBase = w.base(r)
	w.plan, w.script, w.cancel = nil, "", false
	w.planCh = make(chan struct{})
	w.srvSteps, w.srvState, w.srvURL, w.urlState, w.urlError = nil, "", "", "", ""
	w.log.Printf("server %s connected: docker=%q kubectl=%q", f.Hostname, f.Docker, f.Kubectl)
	io.WriteString(rw, "ok\n")
}

func (w *Wizard) handlePlan(rw http.ResponseWriter, r *http.Request) {
	w.mu.Lock()
	ch := w.planCh
	w.mu.Unlock()
	select {
	case <-ch:
	case <-time.After(60 * time.Second):
		rw.WriteHeader(http.StatusNoContent)
		return
	case <-r.Context().Done():
		return
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.cancel || w.script == "" {
		rw.WriteHeader(http.StatusGone)
		return
	}
	w.srvState = "running"
	w.busy = true
	rw.Header().Set("Content-Type", "text/plain; charset=utf-8")
	io.WriteString(rw, w.script)
}

// handleLog takes the installation's reports: "step ID", "ok ID",
// "warn ID CODE", "fail ID CODE" or "done PORT", then optional log lines.
func (w *Wizard) handleLog(rw http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(http.MaxBytesReader(rw, r.Body, 1<<20))
	if err != nil {
		http.Error(rw, err.Error(), http.StatusBadRequest)
		return
	}
	first, detail, _ := strings.Cut(string(body), "\n")
	f := strings.Fields(first)
	if len(f) < 2 {
		http.Error(rw, "bad report", http.StatusBadRequest)
		return
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	switch f[0] {
	case "step":
		w.setStep(&w.srvSteps, f[1], "running", "", "")
	case "ok":
		w.setStep(&w.srvSteps, f[1], "ok", "", "")
	case "warn", "fail":
		code := ""
		if len(f) > 2 {
			code = f[2]
		}
		w.setStep(&w.srvSteps, f[1], map[string]string{"warn": "warn", "fail": "fail"}[f[0]], code, tail(detail, 4000))
		if f[0] == "fail" {
			w.srvState, w.busy = "failed", false
		}
	case "done":
		w.srvPort, _ = strconv.Atoi(f[1])
		w.srvState = "done"
		w.urlState = "checking"
		go w.verifyServer()
	}
	io.WriteString(rw, "ok\n")
}

func tail(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) > n {
		s = "…" + s[len(s)-n:]
	}
	return s
}

// setStep updates (or appends) a step. Callers hold w.mu.
func (w *Wizard) setStep(steps *[]Step, id, status, code, detail string) {
	for i := range *steps {
		if (*steps)[i].ID == id {
			(*steps)[i].Status, (*steps)[i].Code, (*steps)[i].Detail = status, code, detail
			return
		}
	}
	*steps = append(*steps, Step{ID: id, Status: status, Code: code, Detail: detail})
}

// ------------------------------------------------------- choices -> plan

type serverChoice struct {
	Adopt         bool     `json:"adopt"`
	Target        string   `json:"target"`
	InstallDocker bool     `json:"installDocker"`
	MusicDir      string   `json:"musicDir"`
	AutoUpdate    bool     `json:"autoUpdate"`
	Tailscale     bool     `json:"tailscale"`
	Language      string   `json:"language"`
	PC            pcChoice `json:"pc"`
}

func (w *Wizard) handleServerInstall(rw http.ResponseWriter, r *http.Request) {
	var c serverChoice
	if err := readJSON(r, &c); err != nil {
		fail(rw, 400, err.Error())
		return
	}
	if err := c.PC.check(); err != nil {
		fail(rw, 400, err.Error())
		return
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.facts == nil {
		fail(rw, 409, "the server isn't connected yet")
		return
	}
	if w.script != "" || w.cancel {
		fail(rw, 409, "the server already has its instructions: run the command again to start over")
		return
	}
	p := serverscript.Plan{
		Adopt: c.Adopt, Target: c.Target, InstallDocker: c.InstallDocker, MusicDir: c.MusicDir,
		AutoUpdate: c.AutoUpdate, Tailscale: c.Tailscale && w.facts.TailscaleDNS != "",
		Language: c.Language, Token: w.token, Label: w.label, Facts: *w.facts,
	}
	if w.opts.Image != "" {
		p.Image, p.Pull = w.opts.Image, false
	}
	if p.Language != "it" {
		p.Language = "en"
	}
	if p.Target == "docker" && w.facts.Docker == "" && !p.Adopt {
		p.InstallDocker = true
	}
	p.Defaults()
	if p.Port == 0 || (p.Adopt && w.facts.ExistingK8s != nil && len(w.facts.ExistingK8s.Hosts) > 0) {
		// An adopted GetSetMix keeps the address it has: with no port of its
		// own there is nothing to serve, and a host name means it already has one.
		p.Tailscale = false
	}
	script, err := serverscript.Script(w.srvBase, p)
	if err != nil {
		fail(rw, 400, err.Error())
		return
	}
	w.plan, w.script, w.choice = &p, script, c.PC
	w.srvSteps = nil
	for _, id := range p.Steps() {
		w.srvSteps = append(w.srvSteps, Step{ID: id, Status: "pending"})
	}
	w.srvState = "waiting"
	w.busy = true
	w.pcSteps, w.pcState = pcSteps("server", c.PC), ""
	if w.opts.Demo {
		go w.demoServer()
	} else {
		close(w.planCh)
	}
	writeJSON(rw, map[string]any{"steps": p.Steps()})
}

func (w *Wizard) handleServerCancel(rw http.ResponseWriter, r *http.Request) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.script == "" && !w.cancel {
		w.cancel = true
		close(w.planCh)
	}
	writeJSON(rw, map[string]bool{"ok": true})
}

// ---------------------------------------------------------- reachability

// candidates are the addresses this computer may reach the server at, best
// first: HTTPS through Tailscale, the cluster's own host names, then the
// home network.
func (w *Wizard) candidates() []string {
	var out []string
	f, p, port := w.facts, w.plan, w.srvPort
	if f == nil || p == nil {
		return nil
	}
	https := false
	for _, s := range w.srvSteps {
		if s.ID == "https" && s.Status == "ok" {
			https = true
		}
	}
	if https && f.TailscaleDNS != "" {
		u := "https://" + f.TailscaleDNS
		if p.TailscalePort != 443 {
			u += ":" + strconv.Itoa(p.TailscalePort)
		}
		out = append(out, u)
	}
	if p.Adopt && f.ExistingK8s != nil {
		for _, h := range f.ExistingK8s.Hosts {
			out = append(out, "https://"+h, "http://"+h)
		}
	}
	if port > 0 {
		for _, ip := range f.IPs {
			out = append(out, "http://"+net.JoinHostPort(ip, strconv.Itoa(port)))
		}
		if f.TailscaleDNS != "" {
			out = append(out, "http://"+net.JoinHostPort(f.TailscaleDNS, strconv.Itoa(port)))
		}
	}
	return out
}

func (w *Wizard) probe(ctx context.Context, base string) (int, error) {
	c := &fetch.Client{Server: fetch.Server{URL: base, Token: w.token}, HTTP: &http.Client{Timeout: 8 * time.Second}}
	l, err := c.List(ctx)
	if err != nil {
		if strings.Contains(err.Error(), "HTTP 404") {
			return 0, errTooOld
		}
		return 0, err
	}
	return len(l.Files), nil
}

var errTooOld = errors.New("this server runs a GetSetMix too old for direct downloads; it updates itself within the hour, then run Setup again")

func (w *Wizard) verifyServer() {
	w.mu.Lock()
	cands := w.candidates()
	w.mu.Unlock()
	ctx := context.Background()
	start := time.Now()
	var best string
	var files int
	var lastErr error
	for time.Since(start) < 90*time.Second {
		for _, c := range cands {
			n, err := w.probe(ctx, c)
			if err != nil {
				lastErr = err
				continue
			}
			if best == "" || (strings.HasPrefix(c, "https://") && !strings.HasPrefix(best, "https://")) {
				best, files = c, n
			}
			break // candidates are ordered: the first that answers is the best this round
		}
		// Take HTTPS as soon as it answers; settle for plain HTTP only after
		// Tailscale had time to fetch its certificate.
		if strings.HasPrefix(best, "https://") || (best != "" && (time.Since(start) > 40*time.Second || !strings.HasPrefix(cands[0], "https://"))) {
			break
		}
		time.Sleep(3 * time.Second)
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	if best == "" {
		w.urlState = "need"
		if lastErr != nil {
			w.urlError = lastErr.Error()
		}
		return
	}
	w.acceptURL(best, files)
}

// acceptURL records the server's address and goes on with this computer.
// Callers hold w.mu.
func (w *Wizard) acceptURL(u string, files int) {
	w.srvURL, w.srvFiles, w.urlState, w.urlError = u, files, "ok", ""
	go w.runPC("server")
}

func (w *Wizard) handleServerURL(rw http.ResponseWriter, r *http.Request) {
	var req struct{ URL string }
	if err := readJSON(r, &req); err != nil {
		fail(rw, 400, err.Error())
		return
	}
	u := strings.TrimRight(strings.TrimSpace(req.URL), "/")
	if !strings.Contains(u, "://") {
		u = "http://" + u
	}
	if pu, err := url.Parse(u); err != nil || pu.Host == "" || (pu.Scheme != "http" && pu.Scheme != "https") {
		fail(rw, 400, "That doesn't look like an address. Try something like http://192.168.1.10:8765")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()
	n, err := w.probe(ctx, u)
	if err != nil {
		fail(rw, 502, err.Error())
		return
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.urlState == "ok" {
		writeJSON(rw, map[string]bool{"ok": true})
		return
	}
	w.acceptURL(u, n)
	writeJSON(rw, map[string]bool{"ok": true})
}

// handleQR draws the server address as a QR code for the phone.
func (w *Wizard) handleQR(rw http.ResponseWriter, r *http.Request) {
	w.mu.Lock()
	u := w.srvURL
	w.mu.Unlock()
	if u == "" {
		http.NotFound(rw, r)
		return
	}
	code, err := qr.Encode(u, qr.M)
	if err != nil {
		http.Error(rw, err.Error(), 500)
		return
	}
	// SVG, one rect per dark module: crisp at any size, themable.
	n := code.Size
	var b strings.Builder
	fmt.Fprintf(&b, `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 %d %d" shape-rendering="crispEdges"><rect x="-4" y="-4" width="%d" height="%d" fill="#fff"/><path fill="#111" d="`, n+8, n+8, n+8, n+8)
	for y := 0; y < n; y++ {
		for x := 0; x < n; x++ {
			if code.Black(x, y) {
				fmt.Fprintf(&b, "M%d %dh1v1h-1z", x, y)
			}
		}
	}
	b.WriteString(`"/></svg>`)
	rw.Header().Set("Content-Type", "image/svg+xml")
	io.WriteString(rw, b.String())
}

// handleScriptPreview shows what the pasted command runs.
func (w *Wizard) handleScriptPreview(rw http.ResponseWriter, r *http.Request) {
	w.mu.Lock()
	ip := ""
	if len(w.pcIPs) > 0 {
		ip = w.pcIPs[0]
	}
	base := fmt.Sprintf("http://%s/s/%s", net.JoinHostPort(ip, strconv.Itoa(w.pairPort)), w.code)
	w.mu.Unlock()
	rw.Header().Set("Content-Type", "text/plain; charset=utf-8")
	io.WriteString(rw, serverscript.Bootstrap(base))
}
