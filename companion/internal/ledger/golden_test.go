package ledger

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

// The golden files in testdata record each form fetched.json and state.json
// have had (docs/design/library.md, 4.6.1, testing). Each is opened, asked
// the questions, and saved: the answers must be the ones the companion has
// always given, opening and saving again must change nothing, and an older
// companion (frozen* below, a copy of its decoder) must read the saved file
// as it read the original.

// folder is where the server's tracks land in these files.
const folder = "C:/Music"

func local(p string) string { return filepath.Join(folder, filepath.FromSlash(p)) }

func item(id, p string) Item { return Item{ID: id, Path: local(p), Key: track.PathKey(local(p))} }

// golden copies the named testdata files into a fresh companion folder.
func golden(t *testing.T, fetched, synced string) string {
	t.Helper()
	dir := t.TempDir()
	for name, as := range map[string]string{fetched: fetchedFile, synced: syncedFile} {
		data, err := os.ReadFile(filepath.Join("testdata", name))
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, as), data, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return dir
}

// resave opens both files under their locks and saves them unchanged.
func resave(t *testing.T, dir string) {
	t.Helper()
	fl, err := LockFetch(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer fl.Unlock()
	f, err := fl.Load()
	if err != nil {
		t.Fatal(err)
	}
	if err := fl.Save(f); err != nil {
		t.Fatal(err)
	}
	sl, err := LockSync(dir, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer sl.Unlock()
	s, err := sl.Load()
	if err != nil {
		t.Fatal(err)
	}
	if err := sl.Save(s); err != nil {
		t.Fatal(err)
	}
}

func ask(t *testing.T, dir string) (Work, *Fetched, *Synced) {
	t.Helper()
	f, err := ReadFetched(dir)
	if err != nil {
		t.Fatal(err)
	}
	s, err := ReadSynced(dir)
	if err != nil {
		t.Fatal(err)
	}
	return WorkFor(f, s, folder), f, s
}

func read(t *testing.T, dir, name string) []byte {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(dir, name))
	if err != nil {
		t.Fatal(err)
	}
	return data
}

// checkGolden asks dir's files, saves them, asks again and saves once more,
// and checks every round against want and against the older decoder.
func checkGolden(t *testing.T, dir string, want Work, check func(*Fetched, *Synced)) {
	t.Helper()
	oldF, oldS := frozenRead(t, read(t, dir, fetchedFile)), frozenState(t, read(t, dir, syncedFile))
	for round := range 2 {
		w, f, s := ask(t, dir)
		if !reflect.DeepEqual(w, want) {
			t.Fatalf("round %d: work\n%+v\nwant\n%+v", round, w, want)
		}
		check(f, s)
		resave(t, dir)
		if got := frozenRead(t, read(t, dir, fetchedFile)); !reflect.DeepEqual(got, oldF) {
			t.Fatalf("round %d: an older companion reads fetched.json as\n%+v\nnot\n%+v", round, got, oldF)
		}
		if got := frozenState(t, read(t, dir, syncedFile)); !reflect.DeepEqual(got, oldS) {
			t.Fatalf("round %d: an older companion reads state.json as\n%+v\nnot\n%+v", round, got, oldS)
		}
	}
	first, firstS := read(t, dir, fetchedFile), read(t, dir, syncedFile)
	resave(t, dir)
	if !bytes.Equal(first, read(t, dir, fetchedFile)) || !bytes.Equal(firstS, read(t, dir, syncedFile)) {
		t.Fatal("saving a saved file changed it")
	}
}

// A version 1 fetched.json (protocol 1, tracks by path) with a state.json
// whose handled files hold a time alone: no server track waits, the file
// never handled is unhandled, and both stay in their forms when saved.
func TestGoldenVersion1AndTimeOnlySeen(t *testing.T) {
	dir := golden(t, "fetched-v1.json", "state-time-seen.json")
	a := scan.File{Path: "C:/Music/House/a.mp3", Key: "c:/music/house/a.mp3"}
	b := scan.File{Path: "C:/Music/House/b.mp3", Key: "c:/music/house/b.mp3"}
	checkGolden(t, dir, Work{Changed: map[string]Item{}}, func(f *Fetched, s *Synced) {
		if f.Version != 1 || len(f.Legacy) != 2 || f.Skipped[".ogg"] != 2 {
			t.Fatalf("fetched %+v", f)
		}
		if got := s.Unhandled([]scan.File{a, b}); len(got) != 1 || got[0].Key != b.Key {
			t.Fatalf("unhandled %v", got)
		}
		if h := s.Seen[a.Key]; h.Widened() || !h.At.Equal(time.Date(2026, 10, 2, 18, 0, 0, 0, time.UTC)) {
			t.Fatalf("seen %+v", h)
		}
	})
	var v struct {
		Version *int `json:"version"`
	}
	if json.Unmarshal(read(t, dir, fetchedFile), &v); v.Version != nil {
		t.Fatal("a version 1 file was saved as version 2")
	}
}

// A version 2 fetched.json with a tombstone in its first form (the time
// alone) and one in the full form, against a state.json that never listed
// anything: the edited track is changed, and the full tombstone is to be
// listed. The first form names no path, so it lists nothing: that is what
// the companion has always done with it.
func TestGoldenVersion2WithTimeOnlyTombstone(t *testing.T) {
	dir := golden(t, "fetched-v2-time-tombstone.json", "state-time-seen.json")
	edited := item("a1_edited", "House/edited.mp3")
	edited.Was = &track.Tags{Title: "Night Drive", Artist: "Some Artist", Genre: "House", Year: 2019}
	want := Work{
		Changed: map[string]Item{edited.Key: edited},
		Removed: []Item{item("a1_trashed", "House/trashed.mp3")},
	}
	checkGolden(t, dir, want, func(f *Fetched, _ *Synced) {
		if got := f.Removed["a1_gone"]; got.Path != "" || got.At.IsZero() {
			t.Fatalf("first-form tombstone %+v", got)
		}
	})
}

// The same fetched.json against a state.json that listed two tracks and
// holds a widened handled file. The full tombstone's track was never listed
// here, so it is to be listed. Both listed tracks are restored: one has no
// tombstone any more, and the other's is in the first form, which names no
// path.
func TestGoldenStateWithRemoved(t *testing.T) {
	dir := golden(t, "fetched-v2-time-tombstone.json", "state-removed.json")
	edited := item("a1_edited", "House/edited.mp3")
	edited.Was = &track.Tags{Title: "Night Drive", Artist: "Some Artist", Genre: "House", Year: 2019}
	want := Work{
		Changed: map[string]Item{edited.Key: edited},
		Removed: []Item{item("a1_trashed", "House/trashed.mp3")},
		Restored: []Item{
			{Path: "C:/Music/House/back.mp3", Key: "c:/music/house/back.mp3"},
			{Path: "C:/Music/House/gone.mp3", Key: "c:/music/house/gone.mp3"},
		},
	}
	checkGolden(t, dir, want, func(_ *Fetched, s *Synced) {
		if h := s.Seen["c:/music/house/a.mp3"]; !h.Widened() || h.Size != 1234 {
			t.Fatalf("seen %+v", h)
		}
	})
}

// frozen* is the decoder of the companion as it was when the ledger was
// built: the old-companion check. Do not change it with the formats; a test
// that fails here means older companions would misread a file.

type frozenTombstone struct {
	Path     string    `json:"path"`
	At       time.Time `json:"at"`
	Reason   string    `json:"reason,omitempty"`
	Recycle  bool      `json:"recycle,omitempty"`
	Recycled bool      `json:"recycled,omitempty"`
}

func (t *frozenTombstone) UnmarshalJSON(data []byte) error {
	if len(data) > 0 && data[0] == '"' {
		*t = frozenTombstone{}
		return json.Unmarshal(data, &t.At)
	}
	type plain frozenTombstone
	return json.Unmarshal(data, (*plain)(t))
}

type frozenFetched struct {
	Version int                  `json:"version"`
	Fetched map[string]time.Time `json:"fetched"`
	Tracks  map[string]struct {
		Path string    `json:"path"`
		Rev  int64     `json:"rev"`
		At   time.Time `json:"at"`
		Tags *struct {
			Title   string `json:"title"`
			Artist  string `json:"artist"`
			Album   string `json:"album"`
			Genre   string `json:"genre"`
			Year    int    `json:"year,omitempty"`
			Comment string `json:"comment"`
		} `json:"tags,omitempty"`
		Pending bool `json:"pending,omitempty"`
	} `json:"tracks"`
	Legacy  map[string]time.Time       `json:"legacy"`
	Removed map[string]frozenTombstone `json:"removed"`
	Skipped map[string]int             `json:"skipped,omitempty"`
}

func frozenRead(t *testing.T, data []byte) frozenFetched {
	t.Helper()
	var f frozenFetched
	if err := json.Unmarshal(data, &f); err != nil {
		t.Fatalf("an older companion cannot read fetched.json: %v", err)
	}
	return f
}

type frozenHandled struct {
	At    time.Time `json:"at"`
	Size  int64     `json:"size,omitempty"`
	MTime int64     `json:"mtime,omitempty"`
}

func (h *frozenHandled) UnmarshalJSON(data []byte) error {
	if len(data) > 0 && data[0] == '"' {
		*h = frozenHandled{}
		return json.Unmarshal(data, &h.At)
	}
	type plain frozenHandled
	return json.Unmarshal(data, (*plain)(h))
}

type frozenSynced struct {
	Baseline time.Time                `json:"baseline"`
	Seen     map[string]frozenHandled `json:"seen"`
	Removed  map[string]struct {
		Path string    `json:"path"`
		At   time.Time `json:"at"`
	} `json:"removed,omitempty"`
}

func frozenState(t *testing.T, data []byte) frozenSynced {
	t.Helper()
	var s frozenSynced
	if err := json.Unmarshal(data, &s); err != nil {
		t.Fatalf("an older companion cannot read state.json: %v", err)
	}
	if len(s.Removed) == 0 {
		s.Removed = nil // an empty map is saved as absent: the same to an older companion
	}
	return s
}
