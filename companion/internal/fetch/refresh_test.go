package fetch

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Fre0Grella/getsetmix/companion/internal/audio"
	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/library/librarytest"
)

// idOf is the audio id of body saved under name.
func idOf(t *testing.T, name, body string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	id, err := audio.ID(p)
	if err != nil {
		t.Fatal(err)
	}
	return id
}

var (
	before = librarytest.Tags{Title: "Night Drive", Artist: "Some Artist", Genre: "House",
		Comment: "Source: https://example.test | via GetSetMix"}
	after = librarytest.Tags{Title: "Night Drive", Artist: "Some Artist", Genre: "Tech House",
		Year: "2019", Comment: "Source: https://example.test | via GetSetMix"}
)

// A track the server changed (a newer rev for an id this computer holds) is
// downloaded again over the local copy, and the tags seen before are kept for
// the importer (docs/design/library.md, 4.6).
func TestATrackChangedOnTheServerIsFetchedAgain(t *testing.T) {
	v1, v2 := string(librarytest.MP3(1, before)), string(librarytest.MP3(1, after))
	id := idOf(t, "a.mp3", v1)
	if id != idOf(t, "a.mp3", v2) || !strings.HasPrefix(id, "a1_") {
		t.Fatal("a tag edit must keep the audio id")
	}
	s := &server{files: map[string]string{"a.mp3": v1}}
	s.listing = Listing{Protocol: 2, Rev: 5, Files: []File{file("a.mp3", v1, id, 5)}}
	c := s.start(t)
	state := NewState()
	if rep := run(t, c, state); len(rep.Downloaded) != 1 {
		t.Fatalf("first fetch %+v", rep)
	}
	seen := library.Tags{Title: "Night Drive", Artist: "Some Artist", Genre: "House",
		Comment: "Source: https://example.test | via GetSetMix"}
	if got := state.Tracks[id].Tags; got == nil || *got != seen {
		t.Fatalf("tags remembered on the first fetch: %+v", got)
	}

	// Nothing changed: nothing is fetched.
	s.served = nil
	if rep := run(t, c, state); len(s.served) != 0 || len(rep.Updated) != 0 {
		t.Fatalf("an unchanged track was fetched again: %+v", rep)
	}

	// The DJ edits the genre and the year on the server.
	s.files["a.mp3"] = v2
	s.listing = Listing{Protocol: 2, Rev: 9, Files: []File{file("a.mp3", v2, id, 9)}}
	s.served = nil
	rep := run(t, c, state)
	local := filepath.Join(c.Server.Folder, "a.mp3")
	if len(rep.Updated) != 1 || rep.Updated[0] != local || len(rep.Downloaded) != 0 {
		t.Fatalf("report %+v", rep)
	}
	if got, _ := os.ReadFile(local); string(got) != v2 {
		t.Fatal("the local copy was not replaced")
	}
	if got := state.Tracks[id]; got.Rev != 9 || !got.Pending || got.Tags == nil || *got.Tags != seen {
		t.Fatalf("state after the refresh: %+v (the tags seen before must stay)", got)
	}
	if parts, _ := filepath.Glob(filepath.Join(c.Server.Folder, "*.part")); len(parts) != 0 {
		t.Fatalf("left behind: %v", parts)
	}
}

// A newer copy whose audio is not the listed id replaces nothing.
func TestARefreshWithOtherAudioIsRefused(t *testing.T) {
	v1 := string(librarytest.MP3(1, before))
	id := idOf(t, "a.mp3", v1)
	s := &server{files: map[string]string{"a.mp3": v1}}
	s.listing = Listing{Protocol: 2, Rev: 5, Files: []File{file("a.mp3", v1, id, 5)}}
	c := s.start(t)
	state := NewState()
	run(t, c, state)

	other := string(librarytest.MP3(2, after))
	s.files["a.mp3"] = other
	s.listing = Listing{Protocol: 2, Rev: 9, Files: []File{file("a.mp3", other, id, 9)}}
	rep := run(t, c, state)
	if !strings.Contains(rep.Failed["a.mp3"], "audio id") || len(rep.Updated) != 0 {
		t.Fatalf("report %+v", rep)
	}
	if got, _ := os.ReadFile(filepath.Join(c.Server.Folder, "a.mp3")); string(got) != v1 {
		t.Fatal("the local copy was replaced by other audio")
	}
	if state.Tracks[id].Rev != 5 {
		t.Fatal("the rev moved although nothing was fetched: it would not be retried")
	}
	if parts, _ := filepath.Glob(filepath.Join(c.Server.Folder, "*.part")); len(parts) != 0 {
		t.Fatalf("left behind: %v", parts)
	}
}

// A track deleted on this computer stays deleted when the server changes it:
// the new rev is recorded and nothing is downloaded.
func TestAChangedTrackDeletedHereIsNotFetchedAgain(t *testing.T) {
	v1, v2 := string(librarytest.MP3(1, before)), string(librarytest.MP3(1, after))
	id := idOf(t, "a.mp3", v1)
	s := &server{files: map[string]string{"a.mp3": v1}}
	s.listing = Listing{Protocol: 2, Rev: 5, Files: []File{file("a.mp3", v1, id, 5)}}
	c := s.start(t)
	state := NewState()
	run(t, c, state)
	os.Remove(filepath.Join(c.Server.Folder, "a.mp3"))

	s.files["a.mp3"] = v2
	s.listing = Listing{Protocol: 2, Rev: 9, Files: []File{file("a.mp3", v2, id, 9)}}
	s.served = nil
	rep := run(t, c, state)
	if len(s.served) != 0 || len(rep.Updated) != 0 || strings.Join(rep.Kept, ",") != "a.mp3" {
		t.Fatalf("served %v, report %+v", s.served, rep)
	}
	if _, err := os.Stat(filepath.Join(c.Server.Folder, "a.mp3")); !os.IsNotExist(err) {
		t.Fatal("the deleted track came back")
	}
	if state.Tracks[id].Rev != 9 {
		t.Fatalf("rev %d, want 9", state.Tracks[id].Rev)
	}
	s.served = nil
	if run(t, c, state); len(s.served) != 0 {
		t.Fatal("asked again on the next fetch")
	}
}

// A track the server moved and then changed is refreshed where this computer
// keeps it, under the path it was first fetched as.
func TestARefreshLandsAtTheLocalPath(t *testing.T) {
	v1, v2 := string(librarytest.MP3(1, before)), string(librarytest.MP3(1, after))
	id := idOf(t, "a.mp3", v1)
	s := &server{files: map[string]string{"a.mp3": v1}}
	s.listing = Listing{Protocol: 2, Rev: 5, Files: []File{file("a.mp3", v1, id, 5)}}
	c := s.start(t)
	state := NewState()
	run(t, c, state)

	s.files["House/a.mp3"] = v2
	s.listing = Listing{Protocol: 2, Rev: 9, Files: []File{file("House/a.mp3", v2, id, 9)}}
	rep := run(t, c, state)
	if len(rep.Updated) != 1 {
		t.Fatalf("report %+v", rep)
	}
	if got, _ := os.ReadFile(filepath.Join(c.Server.Folder, "a.mp3")); string(got) != v2 {
		t.Fatal("the local copy was not replaced in place")
	}
	if _, err := os.Stat(filepath.Join(c.Server.Folder, "House", "a.mp3")); !os.IsNotExist(err) {
		t.Fatal("a second copy appeared under the server's new path")
	}
}

// A track fetched before tags were remembered gets the tags of its local
// copy, read before the newer copy replaces it.
func TestTagsOfAnOldFetchAreReadBeforeTheRefresh(t *testing.T) {
	v1, v2 := string(librarytest.MP3(1, before)), string(librarytest.MP3(1, after))
	id := idOf(t, "a.mp3", v1)
	s := &server{files: map[string]string{"a.mp3": v2}}
	s.listing = Listing{Protocol: 2, Rev: 9, Files: []File{file("a.mp3", v2, id, 9)}}
	c := s.start(t)
	writeFile(t, c.Server.Folder, "a.mp3", v1)
	state := NewState()
	state.Version = 2
	state.Tracks[id] = Track{Path: "a.mp3", Rev: 5}
	rep := run(t, c, state)
	if len(rep.Updated) != 1 {
		t.Fatalf("report %+v", rep)
	}
	if got := state.Tracks[id].Tags; got == nil || got.Genre != "House" || got.Year != 0 {
		t.Fatalf("tags %+v", got)
	}
}

// Two edits before the importer runs: the tags to compare with stay those of
// the copy Rekordbox has, not of the copy in between.
func TestASecondRefreshKeepsTheBase(t *testing.T) {
	v2, v3 := string(librarytest.MP3(1, before)), string(librarytest.MP3(1, after))
	id := idOf(t, "a.mp3", v2)
	s := &server{files: map[string]string{"a.mp3": v3}}
	s.listing = Listing{Protocol: 2, Rev: 12, Files: []File{file("a.mp3", v3, id, 12)}}
	c := s.start(t)
	// A first newer copy is in place, and nothing is known of the one before it.
	writeFile(t, c.Server.Folder, "a.mp3", v2)
	state := NewState()
	state.Version = 2
	state.Tracks[id] = Track{Path: "a.mp3", Rev: 9, Pending: true}
	run(t, c, state)
	if got := state.Tracks[id]; got.Rev != 12 || got.Tags != nil || !got.Pending {
		t.Fatalf("the copy in between became the base: %+v", got)
	}
}

// A server path replaced by other audio holds two ids; only the newest speaks
// for the file, and a tombstoned track never counts as waiting.
func TestStaleNamesTheNewestTrackOfAPathAndSkipsTombstones(t *testing.T) {
	folder := t.TempDir()
	key := func(p string) string { return library.PathKey(filepath.Join(folder, p)) }
	state := NewState()
	state.Tracks["a1_old"] = Track{Path: "a.mp3", Rev: 3, Pending: true}
	state.Tracks["a1_new"] = Track{Path: "a.mp3", Rev: 8}
	state.Tracks["a1_edited"] = Track{Path: "b.mp3", Rev: 4, Pending: true}
	state.Tracks["a1_removed"] = Track{Path: "c.mp3", Rev: 5, Pending: true}
	state.Removed["a1_removed"] = Tombstone{Path: "c.mp3"}
	got := state.Stale(folder)
	if len(got) != 1 || got[key("b.mp3")] != "a1_edited" {
		t.Fatalf("stale %v", got)
	}
}

// A track removed on the server is not fetched again, whatever its rev was.
func TestATombstonedTrackIsNotFetchedAgain(t *testing.T) {
	v1, v2 := string(librarytest.MP3(1, before)), string(librarytest.MP3(1, after))
	id := idOf(t, "a.mp3", v1)
	s := &server{files: map[string]string{"a.mp3": v1}}
	s.listing = Listing{Protocol: 2, Rev: 5, Files: []File{file("a.mp3", v1, id, 5)}}
	c := s.start(t)
	state := NewState()
	run(t, c, state)

	s.files["a.mp3"] = v2
	s.listing = Listing{Protocol: 2, Rev: 9, Removed: []Removed{
		{ID: id, Path: "a.mp3", At: "2026-11-14T10:00:00+00:00", Reason: "deleted"}}}
	s.served = nil
	rep := run(t, c, state)
	if len(s.served) != 0 || len(rep.Updated) != 0 || state.Tracks[id].Pending {
		t.Fatalf("served %v, report %+v", s.served, rep)
	}
	if _, ok := state.Removed[id]; !ok {
		t.Fatal("no tombstone")
	}
	if got, _ := os.ReadFile(filepath.Join(c.Server.Folder, "a.mp3")); string(got) != v1 {
		t.Fatal("the local copy changed")
	}
}

func TestTheLockIsExclusive(t *testing.T) {
	dir := t.TempDir()
	unlock, err := Lock(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := Lock(dir); err != ErrLocked {
		t.Fatalf("second lock: %v", err)
	}
	unlock()
	again, err := Lock(dir)
	if err != nil {
		t.Fatal(err)
	}
	again()
}
