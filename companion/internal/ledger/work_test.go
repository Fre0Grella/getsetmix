package ledger

import (
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

// A server path replaced by other audio holds two ids; only the newest speaks
// for the file, and a tombstoned track never counts as changed. A changed
// item carries what this computer last saw of its tags.
func TestChangedIsTheNewestTrackOfAPathAndSkipsTombstones(t *testing.T) {
	folder := t.TempDir()
	key := func(p string) string { return track.PathKey(filepath.Join(folder, p)) }
	seen := &track.Tags{Title: "Before"}
	f := NewFetched()
	f.Tracks["a1_old"] = Track{Path: "a.mp3", Rev: 3, Pending: true}
	f.Tracks["a1_new"] = Track{Path: "a.mp3", Rev: 8}
	f.Tracks["a1_edited"] = Track{Path: "b.mp3", Rev: 4, Pending: true, Tags: seen}
	f.Tracks["a1_removed"] = Track{Path: "c.mp3", Rev: 5, Pending: true}
	f.Removed["a1_removed"] = Tombstone{Path: "c.mp3"}
	got := WorkFor(f, NewSynced(time.Now()), folder).Changed
	want := map[string]Item{key("b.mp3"): {ID: "a1_edited", Path: filepath.Join(folder, "b.mp3"),
		Key: key("b.mp3"), Was: seen}}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("changed %+v", got)
	}
}

// A tombstone not listed yet is to be listed; a listed track whose tombstone
// is gone was restored. Once recorded, neither comes back.
func TestRemovedAndRestoredFollowTheTombstones(t *testing.T) {
	folder := t.TempDir()
	local := func(p string) string { return filepath.Join(folder, p) }
	f := NewFetched()
	f.Removed["a1_gone"] = Tombstone{Path: "gone.mp3"}
	f.Removed["a1_listed"] = Tombstone{Path: "listed.mp3"}
	s := NewSynced(time.Now())
	s.Listed(time.Now(),
		Item{Path: local("listed.mp3"), Key: track.PathKey(local("listed.mp3"))},
		Item{Path: local("back.mp3"), Key: track.PathKey(local("back.mp3"))})

	w := WorkFor(f, s, folder)
	if len(w.Removed) != 1 || w.Removed[0].ID != "a1_gone" || w.Removed[0].Path != local("gone.mp3") {
		t.Fatalf("removed %+v", w.Removed)
	}
	if len(w.Restored) != 1 || w.Restored[0].Path != local("back.mp3") {
		t.Fatalf("restored %+v", w.Restored)
	}
	s.Listed(time.Now(), w.Removed...)
	s.Unlisted(w.Restored...)
	if again := WorkFor(f, s, folder); len(again.Removed)+len(again.Restored) != 0 {
		t.Fatalf("recorded work came back: %+v", again)
	}
}

// Without a paired server there is nothing to do about server tracks, even
// with tracks listed from an earlier pairing.
func TestNoServerMeansNoWork(t *testing.T) {
	s := NewSynced(time.Now())
	s.Listed(time.Now(), Item{Path: "x.mp3", Key: "x.mp3"})
	if w := WorkFor(nil, s, ""); len(w.Changed)+len(w.Removed)+len(w.Restored) != 0 {
		t.Fatalf("%+v", w)
	}
}

// A handled file is no longer unhandled; Applied stores the tags and clears
// the wait.
func TestRecordCallsChangeTheAnswers(t *testing.T) {
	s := NewSynced(time.Now())
	a, b := scan.File{Path: "a", Key: "a", Size: 3}, scan.File{Path: "b", Key: "b"}
	s.Handled(time.Now(), a)
	if got := s.Unhandled([]scan.File{a, b}); len(got) != 1 || got[0].Key != "b" {
		t.Fatalf("unhandled %v", got)
	}
	if s.Seen["a"].Size != 3 {
		t.Fatal("the size was not kept")
	}

	f := NewFetched()
	f.Tracks["a1_x"] = Track{Path: "x.mp3", Rev: 2, Pending: true}
	tags := track.Tags{Title: "After"}
	f.Applied(Item{ID: "a1_x"}, tags)
	if got := f.Tracks["a1_x"]; got.Pending || got.Tags == nil || *got.Tags != tags {
		t.Fatalf("after Applied %+v", got)
	}
}
