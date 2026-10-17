package fetch

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

type fakeServer struct {
	files  map[string]string
	served []string
}

func (s *fakeServer) handler(t *testing.T) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/link/files", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer tok" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		var l Listing
		for _, p := range []string{"A - One.mp3", "House/B - Two.mp3", "C - Three.mp3"} {
			if body, ok := s.files[p]; ok {
				l.Files = append(l.Files, File{Path: p, Size: int64(len(body)), MTime: 1_700_000_000})
			}
		}
		json.NewEncoder(w).Encode(l)
	})
	mux.HandleFunc("/api/link/file", func(w http.ResponseWriter, r *http.Request) {
		p := r.URL.Query().Get("path")
		s.served = append(s.served, p)
		w.Write([]byte(s.files[p]))
	})
	return mux
}

func TestRunDownloadsOnceAndRespectsDeletes(t *testing.T) {
	fs := &fakeServer{files: map[string]string{
		"A - One.mp3": "one", "House/B - Two.mp3": "two!", "C - Three.mp3": "three",
	}}
	srv := httptest.NewServer(fs.handler(t))
	defer srv.Close()
	dir := t.TempDir()
	// already here with the right size: adopted, not downloaded
	os.WriteFile(filepath.Join(dir, "C - Three.mp3"), []byte("three"), 0o644)

	c := &Client{Server: Server{URL: srv.URL + "/", Token: "tok", Folder: dir}}
	state := &State{Fetched: map[string]time.Time{}}
	rep, err := c.Run(context.Background(), state, time.Now)
	if err != nil {
		t.Fatal(err)
	}
	if len(rep.Downloaded) != 2 || len(rep.Failed) != 0 || rep.Offered != 3 {
		t.Fatalf("report %+v", rep)
	}
	got, _ := os.ReadFile(filepath.Join(dir, "House", "B - Two.mp3"))
	if string(got) != "two!" {
		t.Fatalf("content %q", got)
	}
	if info, _ := os.Stat(filepath.Join(dir, "A - One.mp3")); info.ModTime().Unix() != 1_700_000_000 {
		t.Fatalf("mtime not kept: %v", info.ModTime())
	}
	if matches, _ := filepath.Glob(filepath.Join(dir, "*.part")); len(matches) != 0 {
		t.Fatalf("leftover parts %v", matches)
	}

	// The DJ deletes a track: the next run must not bring it back.
	os.Remove(filepath.Join(dir, "A - One.mp3"))
	fs.served = nil
	rep, err = c.Run(context.Background(), state, time.Now)
	if err != nil || len(rep.Downloaded) != 0 || len(fs.served) != 0 {
		t.Fatalf("second run: %+v %v served=%v", rep, err, fs.served)
	}
}

func TestShortDownloadIsRetried(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/link/files", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(Listing{Files: []File{{Path: "x.mp3", Size: 10}}})
	})
	mux.HandleFunc("/api/link/file", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("short"))
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()
	dir := t.TempDir()
	c := &Client{Server: Server{URL: srv.URL, Token: "tok", Folder: dir}}
	state := &State{Fetched: map[string]time.Time{}}
	rep, err := c.Run(context.Background(), state, time.Now)
	if err != nil || len(rep.Failed) != 1 || len(state.Fetched) != 0 {
		t.Fatalf("%+v %v", rep, err)
	}
	if entries, _ := os.ReadDir(dir); len(entries) != 0 {
		t.Fatalf("partial file left behind: %v", entries)
	}
}

func TestUnauthorized(t *testing.T) {
	srv := httptest.NewServer((&fakeServer{}).handler(t))
	defer srv.Close()
	c := &Client{Server: Server{URL: srv.URL, Token: "wrong", Folder: t.TempDir()}}
	if _, err := c.Run(context.Background(), &State{Fetched: map[string]time.Time{}}, time.Now); err != ErrUnauthorized {
		t.Fatalf("err = %v", err)
	}
}

func TestLocalRefusesEscapes(t *testing.T) {
	for _, bad := range []string{"../x.mp3", "/etc/x.mp3", "a/../../x.mp3", `a\..\x.mp3`, "", "./x.mp3"} {
		if _, err := Local("/music", bad); err == nil {
			t.Errorf("%q accepted", bad)
		}
	}
	if p, err := Local("dl", "House/x.mp3"); err != nil || p != filepath.Join("dl", "House", "x.mp3") {
		t.Errorf("got %q %v", p, err)
	}
}

func TestStateRoundTrip(t *testing.T) {
	dir := t.TempDir()
	s, err := LoadState(dir)
	if err != nil || len(s.Fetched) != 0 {
		t.Fatal(s, err)
	}
	s.Fetched["a.mp3"] = time.Unix(5, 0)
	if err := s.Save(dir); err != nil {
		t.Fatal(err)
	}
	s2, _ := LoadState(dir)
	if !s2.Fetched["a.mp3"].Equal(time.Unix(5, 0)) {
		t.Fatal(s2)
	}
}
