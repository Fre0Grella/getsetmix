package fetch

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"
)

func tomb(id, path, reason string) Removed {
	return Removed{ID: id, Path: path, At: "2026-11-12T22:10:03+00:00", Reason: reason}
}

// fakeBin stands in for the recycle bin: it moves the file into a folder of
// its own, so a test can tell what was sent there.
type fakeBin struct {
	dir   string
	moved []string
	fail  error
}

func (b *fakeBin) recycle(path string) error {
	if b.fail != nil {
		return b.fail
	}
	b.moved = append(b.moved, path)
	return os.Rename(path, filepath.Join(b.dir, filepath.Base(path)))
}

// both lists the two tracks of twoTracks; onlyA is the listing once the
// server has removed the second one.
var (
	both  = Listing{Protocol: 2, Rev: 5, Files: []File{file("a.mp3", "aaaa", "a1_a", 1), file("House/b.mp3", "bbbbb", "a1_b", 2)}}
	onlyA = Listing{Protocol: 2, Rev: 6, Files: both.Files[:1], Removed: []Removed{tomb("a1_b", "House/b.mp3", "deleted")}}
)

func twoTracks(t *testing.T) (*server, *Client, *State) {
	t.Helper()
	s := &server{files: map[string]string{"a.mp3": "aaaa", "House/b.mp3": "bbbbb"}}
	s.listing = both
	c := s.start(t)
	state := NewState()
	run(t, c, state)
	return s, c, state
}

func TestARemovedTrackIsRecordedOnce(t *testing.T) {
	s, c, state := twoTracks(t)
	s.listing = Listing{Protocol: 2, Rev: 6, Files: []File{file("a.mp3", "aaaa", "a1_a", 1)},
		Removed: []Removed{tomb("a1_b", "House/b.mp3", "deleted"), tomb("a1_never", "x.mp3", "missing")}}

	rep := run(t, c, state)
	if !reflect.DeepEqual(rep.Removed, []string{"House/b.mp3"}) || len(rep.Restored) != 0 {
		t.Fatalf("report %+v", rep)
	}
	want := Tombstone{Path: "House/b.mp3", At: time.Unix(1_800_000_000, 0), Reason: "deleted"}
	if len(state.Removed) != 1 || state.Removed["a1_b"] != want {
		t.Fatalf("removed %+v", state.Removed) // a track never fetched here is not recorded
	}
	// The local file stays: the option is off.
	if _, err := os.Stat(filepath.Join(c.Server.Folder, "House", "b.mp3")); err != nil {
		t.Fatalf("the local file was touched: %v", err)
	}
	// The same listing again: nothing new.
	if rep := run(t, c, state); len(rep.Removed) != 0 || len(state.Removed) != 1 {
		t.Fatalf("handled twice: %+v %+v", rep, state.Removed)
	}
}

func TestARestoreDropsTheTombstone(t *testing.T) {
	s, c, state := twoTracks(t)
	s.listing = onlyA
	run(t, c, state)
	s.listing = both
	s.served = nil
	rep := run(t, c, state)
	if !reflect.DeepEqual(rep.Restored, []string{"House/b.mp3"}) || len(state.Removed) != 0 {
		t.Fatalf("report %+v, removed %+v", rep, state.Removed)
	}
	if len(s.served) != 0 {
		t.Fatalf("a restored track still here was fetched again: %v", s.served)
	}
}

func TestAProtocol1ListingHandlesNoTombstones(t *testing.T) {
	_, c, state := twoTracks(t)
	l := Listing{Files: []File{{Path: "a.mp3", Size: 4}}, Removed: []Removed{tomb("a1_b", "House/b.mp3", "deleted")}}
	var rep Report
	c.tombstones(l, state, time.Now(), &rep)
	if len(state.Removed) != 0 || len(rep.Removed) != 0 {
		t.Fatalf("%+v", state.Removed)
	}
}

func TestATombstoneForAPathKnownFromProtocol1(t *testing.T) {
	s := &server{files: map[string]string{"old.mp3": "oooo"}}
	c := s.start(t)
	state := NewState()
	state.Legacy["old.mp3"] = time.Unix(1_700_000_000, 0)
	s.listing = Listing{Protocol: 2, Removed: []Removed{tomb("a1_o", "old.mp3", "missing")}}
	rep := run(t, c, state)
	if !reflect.DeepEqual(rep.Removed, []string{"old.mp3"}) || state.Removed["a1_o"].Path != "old.mp3" ||
		state.Removed["a1_o"].Reason != "missing" {
		t.Fatalf("report %+v, removed %+v", rep, state.Removed)
	}
}

func TestDeleteTheLocalFileTooSendsItToTheRecycleBin(t *testing.T) {
	s, c, state := twoTracks(t)
	bin := &fakeBin{dir: t.TempDir()}
	c.Recycle = bin.recycle
	c.Server.DeleteRemovedFiles = true
	local := filepath.Join(c.Server.Folder, "House", "b.mp3")
	s.listing = onlyA
	rep := run(t, c, state)
	if !reflect.DeepEqual(bin.moved, []string{local}) || !reflect.DeepEqual(rep.Recycled, []string{local}) {
		t.Fatalf("moved %v, report %+v", bin.moved, rep)
	}
	if got := state.Removed["a1_b"]; !got.Recycled || got.Recycle {
		t.Fatalf("tombstone %+v", got)
	}
	if _, err := os.Stat(filepath.Join(c.Server.Folder, "a.mp3")); err != nil {
		t.Fatalf("a track the server kept was touched: %v", err)
	}
	run(t, c, state)
	if len(bin.moved) != 1 {
		t.Fatalf("recycled twice: %v", bin.moved)
	}

	// Restored on the server: the file this computer recycled is fetched again.
	s.listing = both
	s.served = nil
	rep = run(t, c, state)
	if !reflect.DeepEqual(s.served, []string{"House/b.mp3"}) || len(rep.Downloaded) != 1 {
		t.Fatalf("served %v, report %+v", s.served, rep)
	}
	if data, _ := os.ReadFile(local); string(data) != "bbbbb" {
		t.Fatalf("local file %q", data)
	}
}

func TestTheRecycleBinIsRetriedAndNeverForcesADelete(t *testing.T) {
	s, c, state := twoTracks(t)
	bin := &fakeBin{dir: t.TempDir(), fail: errors.New("the file is in use")}
	c.Recycle = bin.recycle
	c.Server.DeleteRemovedFiles = true
	local := filepath.Join(c.Server.Folder, "House", "b.mp3")
	s.listing = onlyA

	rep := run(t, c, state)
	if rep.Failed["House/b.mp3"] == "" || !state.Removed["a1_b"].Recycle {
		t.Fatalf("report %+v, tombstone %+v", rep, state.Removed["a1_b"])
	}
	if _, err := os.Stat(local); err != nil {
		t.Fatalf("the file must stay when the recycle bin fails: %v", err)
	}
	bin.fail = nil
	run(t, c, state)
	if !reflect.DeepEqual(bin.moved, []string{local}) || !state.Removed["a1_b"].Recycled {
		t.Fatalf("not retried: %v %+v", bin.moved, state.Removed["a1_b"])
	}
}

func TestTurningTheOptionOnLaterLeavesOldTombstonesAlone(t *testing.T) {
	s, c, state := twoTracks(t)
	s.listing = onlyA
	run(t, c, state)
	bin := &fakeBin{dir: t.TempDir()}
	c.Recycle = bin.recycle
	c.Server.DeleteRemovedFiles = true
	run(t, c, state)
	if len(bin.moved) != 0 {
		t.Fatalf("an old tombstone's file was recycled: %v", bin.moved)
	}
}

func TestTombstonesSurviveASaveAndTheFirstForm(t *testing.T) {
	dir := t.TempDir()
	state := NewState()
	state.Version = 2
	state.Removed["a1_b"] = Tombstone{Path: "House/b.mp3", At: time.Unix(1_800_000_000, 0).UTC(),
		Reason: "deleted", Recycled: true}
	if err := state.Save(dir); err != nil {
		t.Fatal(err)
	}
	back, err := LoadState(dir)
	if err != nil || !reflect.DeepEqual(back.Removed, state.Removed) {
		t.Fatalf("%+v, %v", back.Removed, err)
	}
	var old State
	if err := json.Unmarshal([]byte(`{"version": 2, "tracks": {}, "legacy": {},
		"removed": {"a1_9b2e": "2026-11-12T22:15:00Z"}}`), &old); err != nil {
		t.Fatal(err)
	}
	if got := old.Removed["a1_9b2e"]; got.At.IsZero() || got.Path != "" {
		t.Fatalf("%+v", got)
	}
}
