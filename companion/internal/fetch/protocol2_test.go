package fetch

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"
)

// server serves a fixed listing and the bytes of each listed path.
type server struct {
	listing any // marshalled as is: a Listing, or raw JSON
	files   map[string]string
	served  []string
}

func (s *server) start(t *testing.T) *Client {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/link/files", func(w http.ResponseWriter, r *http.Request) {
		if raw, ok := s.listing.(string); ok {
			w.Write([]byte(raw))
			return
		}
		json.NewEncoder(w).Encode(s.listing)
	})
	mux.HandleFunc("/api/link/file", func(w http.ResponseWriter, r *http.Request) {
		p := r.URL.Query().Get("path")
		s.served = append(s.served, p)
		w.Write([]byte(s.files[p]))
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return &Client{Server: Server{URL: srv.URL, Token: "tok", Folder: t.TempDir()}}
}

func file(path, body, id string, rev int64) File {
	return File{Path: path, Size: int64(len(body)), MTime: 1_700_000_000, ID: id, Rev: rev}
}

func writeFile(t *testing.T, dir, rel, body string) {
	t.Helper()
	p := filepath.Join(dir, filepath.FromSlash(rel))
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

func run(t *testing.T, c *Client, state *State) Report {
	t.Helper()
	rep, err := c.Run(context.Background(), state, func() time.Time { return time.Unix(1_800_000_000, 0) })
	if err != nil {
		t.Fatal(err)
	}
	return rep
}

func sorted(paths []string) []string {
	out := append([]string(nil), paths...)
	sort.Strings(out)
	return out
}

func TestProtocol2DownloadsByAudioID(t *testing.T) {
	s := &server{files: map[string]string{"a.mp3": "aaaa", "b.flac": "bbbbb"}}
	s.listing = Listing{Protocol: 2, Rev: 9, Files: []File{
		file("a.mp3", "aaaa", "a1_a", 3), file("b.flac", "bbbbb", "a1_b", 9),
	}}
	c := s.start(t)
	state := NewState()
	rep := run(t, c, state)
	if len(rep.Downloaded) != 2 || rep.Offered != 2 {
		t.Fatalf("report %+v", rep)
	}
	if state.Version != 2 || state.Tracks["a1_a"] != (Track{Path: "a.mp3", Rev: 3, At: time.Unix(1_800_000_000, 0)}) ||
		state.Tracks["a1_b"].Rev != 9 || len(state.Legacy) != 0 {
		t.Fatalf("state %+v", state)
	}

	// The server renames a track: same audio, so it is not fetched again.
	s.listing = Listing{Protocol: 2, Rev: 10, Files: []File{
		file("House/a renamed.mp3", "aaaa", "a1_a", 3), file("b.flac", "bbbbb", "a1_b", 9),
	}}
	s.files["House/a renamed.mp3"] = "aaaa"
	s.served = nil
	if rep := run(t, c, state); len(rep.Downloaded) != 0 || len(s.served) != 0 {
		t.Fatalf("renamed track fetched again: %+v %v", rep, s.served)
	}
}

func TestDeletingHereSticksUnderProtocol2(t *testing.T) {
	s := &server{files: map[string]string{"a.mp3": "aaaa"}}
	s.listing = Listing{Protocol: 2, Files: []File{file("a.mp3", "aaaa", "a1_a", 1)}}
	c := s.start(t)
	state := NewState()
	run(t, c, state)
	os.Remove(filepath.Join(c.Server.Folder, "a.mp3"))
	s.served = nil
	if rep := run(t, c, state); len(rep.Downloaded) != 0 || len(s.served) != 0 {
		t.Fatalf("deleted track came back: %+v", rep)
	}
}

// A listing that mixes files Rekordbox imports with files it cannot (#31):
// only the first kind is downloaded, and the rest is counted for `status`.
func TestFilesRekordboxCannotImportAreSkipped(t *testing.T) {
	bodies := map[string]string{
		"a.mp3": "a", "b.flac": "bb", "c.ogg": "ccc", "d.opus": "dddd", "e.OGG": "eeeee", "f.wav": "ff",
	}
	for _, protocol := range []int{1, 2} {
		s := &server{files: bodies}
		var files []File
		for _, p := range []string{"a.mp3", "b.flac", "c.ogg", "d.opus", "e.OGG", "f.wav"} {
			f := file(p, bodies[p], "", 0)
			if protocol == 2 {
				f.ID, f.Rev = "a1_"+p, 1
			}
			files = append(files, f)
		}
		s.listing = Listing{Protocol: protocol, Files: files}
		c := s.start(t)
		state := NewState()
		rep := run(t, c, state)

		if got := sorted(s.served); strings.Join(got, ",") != "a.mp3,b.flac,f.wav" {
			t.Fatalf("protocol %d: served %v", protocol, got)
		}
		if rep.Offered != 3 || rep.Skipped[".ogg"] != 2 || rep.Skipped[".opus"] != 1 {
			t.Fatalf("protocol %d: report %+v", protocol, rep)
		}
		for _, p := range []string{"c.ogg", "d.opus", "e.OGG"} {
			if _, err := os.Stat(filepath.Join(c.Server.Folder, p)); err == nil {
				t.Errorf("protocol %d: %s downloaded", protocol, p)
			}
		}
		want := "3 file(s) Rekordbox cannot import (2 ogg, 1 opus): not downloaded, kept on the server"
		if got := state.SkippedSummary(); got != want {
			t.Fatalf("protocol %d: summary %q", protocol, got)
		}
		// `status` reads it back from the saved state.
		dir := t.TempDir()
		if err := state.Save(dir); err != nil {
			t.Fatal(err)
		}
		again, err := LoadState(dir)
		if err != nil || again.SkippedSummary() != want {
			t.Fatalf("protocol %d: after a reload %q %v", protocol, again.SkippedSummary(), err)
		}
		// Skipped files are not remembered as fetched: should Rekordbox learn
		// to import them, the next fetch downloads them.
		if state.Has(files[2]) {
			t.Fatalf("protocol %d: a skipped file counts as fetched", protocol)
		}
	}
	if (&State{}).SkippedSummary() != "" {
		t.Fatal("summary with nothing skipped")
	}
}

// A new companion against a server from before link protocol 2.
func TestProtocol1ServerKeepsTheVersion1State(t *testing.T) {
	s := &server{files: map[string]string{"a.mp3": "aaaa", "b.mp3": "bb"}}
	// What an old server answers: no protocol, no ids.
	s.listing = `{"version":"1.9.0","files":[{"path":"a.mp3","size":4,"mtime":1700000000},` +
		`{"path":"b.mp3","size":2,"mtime":1700000000}]}`
	c := s.start(t)
	home := t.TempDir()
	state, _ := LoadState(home)
	rep := run(t, c, state)
	if len(rep.Downloaded) != 2 {
		t.Fatalf("report %+v", rep)
	}
	if err := state.Save(home); err != nil {
		t.Fatal(err)
	}
	var onDisk map[string]json.RawMessage
	data, _ := os.ReadFile(filepath.Join(home, stateFile))
	json.Unmarshal(data, &onDisk)
	if _, ok := onDisk["fetched"]; !ok || onDisk["version"] != nil || onDisk["tracks"] != nil {
		t.Fatalf("not a version 1 file: %s", data)
	}
	if _, err := os.Stat(filepath.Join(home, stateFileV1)); err == nil {
		t.Fatal("fetched.v1.json written without a migration")
	}
	state, _ = LoadState(home)
	s.served = nil
	if rep := run(t, c, state); len(rep.Downloaded) != 0 || len(s.served) != 0 {
		t.Fatalf("fetched again: %+v", rep)
	}
}

// An old companion reads a protocol 2 listing with its own types, which know
// path, size and mtime only, and gets what an old server would have said.
func TestAnOldCompanionReadsAProtocol2Listing(t *testing.T) {
	body := `{"version":"1.11.0","protocol":2,"rev":4812,
	  "files":[{"path":"Artist - Title.mp3","size":12518400,"mtime":1794517450,
	            "id":"a1_3f9c0d2a7b1e4c5d8a6f0b9e2d7c1a45","rev":4790}],
	  "removed":[{"id":"a1_9b2e","path":"Other - Track.mp3",
	              "at":"2026-11-12T22:10:03+00:00","reason":"deleted"}]}`
	type oldFile struct {
		Path  string `json:"path"`
		Size  int64  `json:"size"`
		MTime int64  `json:"mtime"`
	}
	var old struct {
		Version string    `json:"version"`
		Files   []oldFile `json:"files"`
	}
	if err := json.NewDecoder(strings.NewReader(body)).Decode(&old); err != nil {
		t.Fatal(err)
	}
	if len(old.Files) != 1 || old.Files[0] != (oldFile{"Artist - Title.mp3", 12518400, 1794517450}) {
		t.Fatalf("old reading %+v", old)
	}
	// And this companion reads all of it.
	var l Listing
	if err := json.Unmarshal([]byte(body), &l); err != nil {
		t.Fatal(err)
	}
	if !l.ByID() || l.Rev != 4812 || l.Files[0].ID != "a1_3f9c0d2a7b1e4c5d8a6f0b9e2d7c1a45" ||
		l.Files[0].Rev != 4790 || len(l.Removed) != 1 || l.Removed[0].Reason != "deleted" {
		t.Fatalf("listing %+v", l)
	}
}

// The first fetch against a protocol 2 server migrates fetched.json
// (docs/design/library.md, 4.6).
func TestMigrationToVersion2(t *testing.T) {
	s := &server{files: map[string]string{
		"same.mp3": "same", "edited.mp3": "edited on the server", "deleted here.mp3": "x",
		"new.mp3": "new", "x.ogg": "ogg",
	}}
	s.listing = Listing{Protocol: 2, Rev: 50, Files: []File{
		file("same.mp3", "same", "a1_same", 10),
		file("edited.mp3", "edited on the server", "a1_edited", 40),
		file("deleted here.mp3", "x", "a1_deleted", 11),
		file("new.mp3", "new", "a1_new", 45),
		file("x.ogg", "ogg", "f1_ogg", 46),
	}}
	c := s.start(t)
	home := t.TempDir()
	v1 := []byte(`{
  "fetched": {
    "same.mp3": "2026-10-01T18:00:00Z",
    "edited.mp3": "2026-10-02T18:00:00Z",
    "deleted here.mp3": "2026-10-03T18:00:00Z",
    "Gone From Server.mp3": "2026-10-04T18:00:00Z"
  }
}
`)
	os.WriteFile(filepath.Join(home, stateFile), v1, 0o644)
	writeFile(t, c.Server.Folder, "same.mp3", "same")
	writeFile(t, c.Server.Folder, "edited.mp3", "old bytes") // the local size differs
	// "deleted here.mp3" was deleted by the DJ.

	state, err := LoadState(home)
	if err != nil || state.Version != 1 || len(state.Legacy) != 4 {
		t.Fatalf("v1 state %+v %v", state, err)
	}
	rep := run(t, c, state)
	if err := state.Save(home); err != nil {
		t.Fatal(err)
	}

	// Behaviour does not change in this slice: only the new track is fetched.
	if strings.Join(s.served, ",") != "new.mp3" || len(rep.Downloaded) != 1 {
		t.Fatalf("served %v, report %+v", s.served, rep)
	}
	at := func(day int) time.Time { return time.Date(2026, 10, day, 18, 0, 0, 0, time.UTC) }
	want := map[string]Track{
		"a1_same":    {Path: "same.mp3", Rev: 10, At: at(1)},
		"a1_edited":  {Path: "edited.mp3", Rev: 0, At: at(2)},
		"a1_deleted": {Path: "deleted here.mp3", Rev: 0, At: at(3)},
		"a1_new":     {Path: "new.mp3", Rev: 45, At: time.Unix(1_800_000_000, 0)},
	}
	state, _ = LoadState(home)
	if state.Version != 2 || len(state.Tracks) != len(want) {
		t.Fatalf("v2 state %+v", state)
	}
	for id, w := range want {
		if got := state.Tracks[id]; got.Path != w.Path || got.Rev != w.Rev || !got.At.Equal(w.At) {
			t.Errorf("%s: %+v, want %+v", id, got, w)
		}
	}
	if len(state.Legacy) != 1 || !state.Legacy["Gone From Server.mp3"].Equal(at(4)) {
		t.Errorf("legacy %v", state.Legacy)
	}
	if state.Removed == nil || len(state.Removed) != 0 {
		t.Errorf("removed %v", state.Removed)
	}

	kept, err := os.ReadFile(filepath.Join(home, stateFileV1))
	if err != nil || !bytes.Equal(kept, v1) {
		t.Fatalf("fetched.v1.json %q %v", kept, err)
	}
	var onDisk map[string]json.RawMessage
	data, _ := os.ReadFile(filepath.Join(home, stateFile))
	json.Unmarshal(data, &onDisk)
	for _, k := range []string{"version", "tracks", "legacy", "removed"} {
		if onDisk[k] == nil {
			t.Errorf("fetched.json has no %q: %s", k, data)
		}
	}
	if string(onDisk["version"]) != "2" || onDisk["fetched"] != nil {
		t.Errorf("fetched.json: %s", data)
	}

	// Saving again leaves the kept file alone.
	if err := state.Save(home); err != nil {
		t.Fatal(err)
	}
	if again, _ := os.ReadFile(filepath.Join(home, stateFileV1)); !bytes.Equal(again, v1) {
		t.Fatal("fetched.v1.json overwritten")
	}

	// A path that left the listing and comes back is still not fetched.
	s.listing = Listing{Protocol: 2, Rev: 51, Files: []File{
		file("Gone From Server.mp3", "back", "a1_back", 51),
	}}
	s.files["Gone From Server.mp3"] = "back"
	s.served = nil
	if rep := run(t, c, state); len(s.served) != 0 || len(rep.Downloaded) != 0 {
		t.Fatalf("legacy path fetched: %v", s.served)
	}
	if state.Tracks["a1_back"].Path != "Gone From Server.mp3" || len(state.Legacy) != 0 {
		t.Fatalf("legacy path not tied to its id: %+v", state)
	}
}

// A version 2 state against a server that answers protocol 1 (one whose
// index is not built yet): tracks are matched by path, nothing known is
// fetched again, and a new track is tied to its id once protocol 2 is back.
func TestVersion2StateAgainstAProtocol1Listing(t *testing.T) {
	s := &server{files: map[string]string{"a.mp3": "aaaa", "b.mp3": "bb"}}
	s.listing = Listing{Protocol: 2, Files: []File{file("a.mp3", "aaaa", "a1_a", 1)}}
	c := s.start(t)
	state := NewState()
	run(t, c, state)

	s.listing = Listing{Files: []File{file("a.mp3", "aaaa", "", 0), file("b.mp3", "bb", "", 0)}}
	s.served = nil
	run(t, c, state)
	if strings.Join(s.served, ",") != "b.mp3" || state.Version != 2 || !state.Legacy["b.mp3"].Equal(time.Unix(1_800_000_000, 0)) {
		t.Fatalf("served %v, state %+v", s.served, state)
	}

	s.listing = Listing{Protocol: 2, Files: []File{file("a.mp3", "aaaa", "a1_a", 1), file("b.mp3", "bb", "a1_b", 2)}}
	s.served = nil
	run(t, c, state)
	if len(s.served) != 0 || state.Tracks["a1_b"].Rev != 2 || len(state.Legacy) != 0 {
		t.Fatalf("served %v, state %+v", s.served, state)
	}
}
