package ledger

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

func wantedMP3(p string) bool { return strings.HasSuffix(p, ".mp3") }

func place(t *testing.T, folder, p string) string {
	t.Helper()
	dest := filepath.Join(folder, filepath.FromSlash(p))
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(dest, []byte("mp3"), 0o644); err != nil {
		t.Fatal(err)
	}
	return dest
}

func kinds(steps []Step) map[string]StepKind {
	out := map[string]StepKind{}
	for _, s := range steps {
		out[s.File.Path] = s.Kind
	}
	return out
}

// A protocol 2 listing: a new track is fetched, a newer copy of one held
// here replaces it, a newer copy of one deleted here is only noted, a track
// listed twice (one audio at two server paths) is fetched once, and what
// Rekordbox cannot import is counted, not fetched. Planning changes no
// track the state holds.
func TestPlanSaysWhatToFetch(t *testing.T) {
	folder := t.TempDir()
	place(t, folder, "House/held.mp3")
	s := NewFetched()
	s.Version = 2
	s.Tracks["a1_held"] = Track{Path: "House/held.mp3", Rev: 3, Tags: &track.Tags{Title: "Seen"}}
	s.Tracks["a1_deleted"] = Track{Path: "House/deleted.mp3", Rev: 2}
	s.Tracks["a1_same"] = Track{Path: "House/same.mp3", Rev: 1}
	before := len(s.Tracks)

	l := track.Listing{Protocol: 2, Files: []track.File{
		{Path: "House/held.mp3", ID: "a1_held", Rev: 5},
		{Path: "House/deleted.mp3", ID: "a1_deleted", Rev: 4},
		{Path: "House/same.mp3", ID: "a1_same", Rev: 1},
		{Path: "House/new.mp3", ID: "a1_new", Rev: 6},
		{Path: "Copies/new.mp3", ID: "a1_new", Rev: 6},
		{Path: "House/voice.ogg", ID: "a1_ogg", Rev: 1},
	}}
	p := s.Plan(l, folder, wantedMP3, false, time.Now())
	want := map[string]StepKind{"House/held.mp3": Refresh, "House/deleted.mp3": Keep, "House/new.mp3": Get}
	if got := kinds(p.Steps); !reflect.DeepEqual(got, want) {
		t.Fatalf("steps %v", got)
	}
	if p.Offered != 5 || !reflect.DeepEqual(p.Skipped, map[string]int{".ogg": 1}) {
		t.Fatalf("offered %d, skipped %v", p.Offered, p.Skipped)
	}
	for _, st := range p.Steps {
		if st.File.Path == "House/held.mp3" && st.NeedTags {
			t.Error("the tags of a copy whose tags are known were asked for")
		}
	}
	if len(s.Tracks) != before || s.Tracks["a1_held"].Rev != 3 {
		t.Fatalf("planning changed the tracks: %+v", s.Tracks)
	}
}

// A track the server removed is tombstoned only when this computer holds
// it; with the option on, a deleted one's file is to go to the recycle bin,
// a missing one's never. A tombstone the server lists again is restored, and
// one whose file went to the recycle bin is fetched again.
func TestPlanHandlesTombstones(t *testing.T) {
	folder := t.TempDir()
	trashed := place(t, folder, "House/trashed.mp3")
	place(t, folder, "House/vanished.mp3")
	s := NewFetched()
	s.Version = 2
	s.Tracks["a1_trashed"] = Track{Path: "House/trashed.mp3", Rev: 1}
	s.Tracks["a1_vanished"] = Track{Path: "House/vanished.mp3", Rev: 1}
	s.Tracks["a1_back"] = Track{Path: "House/back.mp3", Rev: 1}
	s.Removed["a1_back"] = Tombstone{Path: "House/back.mp3", Recycled: true}

	l := track.Listing{Protocol: 2,
		Files: []track.File{{Path: "House/back.mp3", ID: "a1_back", Rev: 1}},
		Removed: []track.Tombstone{
			{ID: "a1_trashed", Path: "House/trashed.mp3", Reason: "deleted"},
			{ID: "a1_vanished", Path: "House/vanished.mp3", Reason: "missing"},
			{ID: "a1_stranger", Path: "House/stranger.mp3", Reason: "deleted"},
		}}
	now := time.Now()
	p := s.Plan(l, folder, wantedMP3, true, now)

	if len(p.Tombstones) != 2 || !p.Tombstones["a1_trashed"].Recycle || p.Tombstones["a1_vanished"].Recycle {
		t.Fatalf("tombstones %+v", p.Tombstones)
	}
	if !reflect.DeepEqual(p.Recycle, []Recycle{{ID: "a1_trashed", Path: "House/trashed.mp3", Dest: trashed}}) {
		t.Fatalf("recycle %+v", p.Recycle)
	}
	if !reflect.DeepEqual(p.Restored, []Restore{{ID: "a1_back", Path: "House/back.mp3", Refetch: true}}) {
		t.Fatalf("restored %+v", p.Restored)
	}
	if got := kinds(p.Steps); !reflect.DeepEqual(got, map[string]StepKind{"House/back.mp3": Get}) {
		t.Fatalf("steps %v", got)
	}
	if len(s.Removed) != 1 {
		t.Fatal("planning recorded a tombstone")
	}

	// The record calls, as fetch makes them.
	s.Restored(p.Restored[0])
	for id, tomb := range p.Tombstones {
		s.Tombstoned(id, tomb)
	}
	s.Recycled("a1_trashed", true)
	if _, ok := s.Tracks["a1_back"]; ok {
		t.Fatal("a track to fetch again was kept")
	}
	if got := s.Removed["a1_trashed"]; got.Recycle || !got.Recycled || !got.At.Equal(now) {
		t.Fatalf("recycled tombstone %+v", got)
	}
	if again := s.Plan(l, folder, wantedMP3, true, now); len(again.Tombstones)+len(again.Recycle) != 0 {
		t.Fatalf("recorded tombstones planned again: %+v", again)
	}
}

// A newer copy of a track fetched before tags were remembered asks for the
// old copy's tags; Refreshed keeps them as the base, and a second newer copy
// before the importer ran keeps the first base.
func TestRefreshKeepsTheTagsRekordboxHas(t *testing.T) {
	folder := t.TempDir()
	place(t, folder, "a.mp3")
	s := NewFetched()
	s.Version = 2
	s.Tracks["a1_a"] = Track{Path: "a.mp3", Rev: 1}
	l := track.Listing{Protocol: 2, Files: []track.File{{Path: "a.mp3", ID: "a1_a", Rev: 2}}}
	p := s.Plan(l, folder, wantedMP3, false, time.Now())
	if len(p.Steps) != 1 || !p.Steps[0].NeedTags {
		t.Fatalf("steps %+v", p.Steps)
	}
	base := &track.Tags{Title: "Imported"}
	s.Refreshed(p.Steps[0].File, time.Now(), base)
	if got := s.Tracks["a1_a"]; got.Rev != 2 || !got.Pending || got.Tags != base {
		t.Fatalf("after one refresh %+v", got)
	}
	l.Files[0].Rev = 3
	p = s.Plan(l, folder, wantedMP3, false, time.Now())
	if p.Steps[0].NeedTags {
		t.Fatal("the tags of a copy Rekordbox has not seen were asked for")
	}
	s.Refreshed(p.Steps[0].File, time.Now(), &track.Tags{Title: "In between"})
	if got := s.Tracks["a1_a"]; got.Rev != 3 || got.Tags != base {
		t.Fatalf("after two refreshes %+v", got)
	}
}
