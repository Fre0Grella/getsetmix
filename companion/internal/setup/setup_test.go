package setup

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/fetch"
)

func newWizard(t *testing.T) *Wizard {
	t.Helper()
	home := t.TempDir()
	t.Setenv("GSM_COMPANION_HOME", home)
	exe := filepath.Join(t.TempDir(), "setup.exe")
	os.WriteFile(exe, []byte("pretend companion"), 0o755)
	w := &Wizard{
		opts: Options{Home: home, Exe: exe, DryRunOS: true, Version: "dev"},
		log:  log.New(io.Discard, "", 0), key: "k3y", code: "abcd2345",
		planCh: make(chan struct{}), token: randomKey(32), label: "Test PC",
	}
	w.pc = pcInfo{Name: "Test PC", MusicDefault: filepath.Join(home, "Music")}
	return w
}

// ui returns a client already holding the page's session cookie.
func ui(t *testing.T, w *Wizard) (*httptest.Server, *http.Client) {
	t.Helper()
	srv := httptest.NewServer(w.uiHandler())
	t.Cleanup(srv.Close)
	jar := &cookieJar{}
	c := &http.Client{Jar: jar}
	resp, err := c.Get(srv.URL + "/?k=" + w.key)
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	return srv, c
}

type cookieJar struct{ cookies []*http.Cookie }

func (j *cookieJar) SetCookies(_ *url.URL, c []*http.Cookie) { j.cookies = append(j.cookies, c...) }
func (j *cookieJar) Cookies(*url.URL) []*http.Cookie         { return j.cookies }

func postJSON(t *testing.T, c *http.Client, u string, body any) (*http.Response, map[string]any) {
	t.Helper()
	data, _ := json.Marshal(body)
	resp, err := c.Post(u, "application/json", bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var out map[string]any
	json.NewDecoder(resp.Body).Decode(&out)
	return resp, out
}

func TestUIRefusesStrangers(t *testing.T) {
	w := newWizard(t)
	srv, c := ui(t, w)
	if resp, _ := http.Get(srv.URL + "/api/state"); resp.StatusCode != http.StatusForbidden {
		t.Fatalf("no cookie: %d", resp.StatusCode)
	}
	req, _ := http.NewRequest("GET", srv.URL+"/api/state", nil)
	req.Host = "evil.example:80" // DNS rebinding
	if resp, _ := c.Do(req); resp.StatusCode != http.StatusForbidden {
		t.Fatalf("foreign host: %d", resp.StatusCode)
	}
	resp, err := c.Post(srv.URL+"/api/server/cancel", "text/plain", strings.NewReader("{}"))
	if err != nil || resp.StatusCode != http.StatusUnsupportedMediaType {
		t.Fatalf("form post: %v %d", err, resp.StatusCode)
	}
	if resp, _ := c.Get(srv.URL + "/api/state"); resp.StatusCode != http.StatusOK {
		t.Fatalf("with cookie: %d", resp.StatusCode)
	}
}

func TestPairRefusesWrongCode(t *testing.T) {
	w := newWizard(t)
	srv := httptest.NewServer(w.pairHandler())
	defer srv.Close()
	if resp, _ := http.Get(srv.URL + "/s/wrongcode"); resp.StatusCode != http.StatusNotFound {
		t.Fatalf("wrong code: %d", resp.StatusCode)
	}
	resp, _ := http.Get(srv.URL + "/s/" + w.code)
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "BASE='http://"+strings.TrimPrefix(srv.URL, "http://")+"/s/"+w.code+"'") {
		t.Fatalf("bootstrap doesn't point back at Setup:\n%s", body)
	}
}

// fakeGSM is a GetSetMix server with one track and the link API.
func fakeGSM(t *testing.T, token string) *httptest.Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/link/files", func(rw http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+token {
			rw.WriteHeader(401)
			return
		}
		json.NewEncoder(rw).Encode(fetch.Listing{Version: "1.6.0", Files: []fetch.File{{Path: "House/A - B.mp3", Size: 5}}})
	})
	mux.HandleFunc("/api/link/file", func(rw http.ResponseWriter, r *http.Request) { rw.Write([]byte("audio")) })
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

// TestServerFlow plays the whole "home server" path: the server reports its
// facts, the person chooses, the server takes the plan and reports each
// step, Setup finds the server and sets this computer up.
func TestServerFlow(t *testing.T) {
	w := newWizard(t)
	gsm := fakeGSM(t, w.token)
	gsmURL, _ := url.Parse(gsm.URL)
	host, port := gsmURL.Hostname(), gsmURL.Port()

	pair := httptest.NewServer(w.pairHandler())
	defer pair.Close()
	srv, c := ui(t, w)
	base := pair.URL + "/s/" + w.code

	facts := "hostname=nas\nos=Debian 12\narch=x86_64\nips=" + host + "\ndocker=27.0.1\nlistening=22\n"
	if resp, err := http.Post(base+"/facts", "text/plain", strings.NewReader(facts)); err != nil || resp.StatusCode != 200 {
		t.Fatalf("facts: %v", err)
	}

	// The server waits for the plan while the person chooses.
	planCh := make(chan string, 1)
	go func() {
		resp, err := http.Get(base + "/plan")
		if err != nil {
			planCh <- "error: " + err.Error()
			return
		}
		b, _ := io.ReadAll(resp.Body)
		planCh <- string(b)
	}()

	music := filepath.Join(w.opts.Home, "Music")
	resp, out := postJSON(t, c, srv.URL+"/api/server/install", map[string]any{
		"target": "docker", "musicDir": "/srv/music", "autoUpdate": true, "language": "it",
		"pc": map[string]any{"folder": music, "delivery": "download", "copyExisting": true},
	})
	if resp.StatusCode != 200 {
		t.Fatalf("install: %d %v", resp.StatusCode, out)
	}
	var script string
	select {
	case script = <-planCh:
	case <-time.After(5 * time.Second):
		t.Fatal("the server never got its plan")
	}
	for _, want := range []string{"BASE='" + base + "'", "'/srv/music':/music", "GSM_LANGUAGE='it'", w.token} {
		if !strings.Contains(script, want) {
			t.Errorf("plan lacks %q", want)
		}
	}

	report := func(line string) {
		if resp, err := http.Post(base+"/log", "text/plain", strings.NewReader(line)); err != nil || resp.StatusCode != 200 {
			t.Fatalf("log %q: %v", line, err)
		}
	}
	for _, id := range []string{"folders", "app", "updates", "start", "link"} {
		report("step " + id + "\n")
		report("ok " + id + "\n")
	}
	report("done " + port + "\n")

	var st stateView
	deadline := time.Now().Add(20 * time.Second)
	for time.Now().Before(deadline) {
		r, _ := c.Get(srv.URL + "/api/state")
		st = stateView{}
		json.NewDecoder(r.Body).Decode(&st)
		r.Body.Close()
		if st.Local.State == "done" || st.Local.State == "failed" {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if st.Server.URL != "http://"+host+":"+port || st.Server.URLState != "ok" {
		t.Fatalf("server address: %+v", st.Server)
	}
	if st.Local.State != "done" {
		t.Fatalf("this computer: %+v", st.Local)
	}

	cfg, err := config.Load(w.opts.Home)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Server == nil || cfg.Server.Token != w.token || cfg.Server.Folder != music || cfg.Folders[0] != music {
		t.Fatalf("config %+v %+v", cfg, cfg.Server)
	}
	if !strings.HasPrefix(cfg.RekordboxDir, w.opts.Home) {
		t.Fatalf("a dry run must not point at the real Rekordbox: %q", cfg.RekordboxDir)
	}
	if got, _ := os.ReadFile(filepath.Join(music, "House", "A - B.mp3")); string(got) != "audio" {
		t.Fatalf("first download: %q", got)
	}
	if _, err := os.Stat(filepath.Join(w.opts.Home, "programs")); err != nil {
		t.Fatalf("companion not placed: %v", err)
	}
}

func TestCancelTellsTheServer(t *testing.T) {
	w := newWizard(t)
	pair := httptest.NewServer(w.pairHandler())
	defer pair.Close()
	base := pair.URL + "/s/" + w.code
	http.Post(base+"/facts", "text/plain", strings.NewReader("hostname=x\n"))
	done := make(chan int, 1)
	go func() {
		resp, err := http.Get(base + "/plan")
		if err != nil {
			done <- 0
			return
		}
		done <- resp.StatusCode
	}()
	time.Sleep(100 * time.Millisecond)
	w.finish()
	if code := <-done; code != http.StatusGone {
		t.Fatalf("plan after cancel: %d", code)
	}
}

func TestPCChoiceCheck(t *testing.T) {
	abs, _ := filepath.Abs("music")
	for _, c := range []pcChoice{{Folder: ""}, {Folder: "relative"}, {Folder: abs, Delivery: "carrier pigeon"},
		{Folder: abs, Playlist: "a/b"}} {
		if c.check() == nil {
			t.Errorf("%+v accepted", c)
		}
	}
	c := pcChoice{Folder: abs}
	if err := c.check(); err != nil || c.Delivery != "download" || c.Playlist != "GetSetMix" {
		t.Fatalf("%+v %v", c, err)
	}
}

func TestRandomCode(t *testing.T) {
	seen := map[string]bool{}
	for i := 0; i < 200; i++ {
		c := randomCode()
		if len(c) != 8 || strings.ContainsAny(c, "il1o") || seen[c] {
			t.Fatalf("code %q", c)
		}
		seen[c] = true
	}
}

func TestWriteAppSettingsKeepsOthers(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "config.json"), []byte(`{"language": "it", "library_root": "/old"}`), 0o644)
	if err := writeAppSettings(dir, `C:\Music\GSM`); err != nil {
		t.Fatal(err)
	}
	var got map[string]any
	data, _ := os.ReadFile(filepath.Join(dir, "config.json"))
	json.Unmarshal(data, &got)
	if got["language"] != "it" || got["library_root"] != `C:\Music\GSM` {
		t.Fatalf("%v", got)
	}
}
