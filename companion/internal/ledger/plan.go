package ledger

import (
	"os"
	"path"
	"sort"
	"strings"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

// StepKind is what a fetch does with one listed track.
type StepKind int

const (
	// Get downloads a track this computer has not fetched before, unless a
	// file of its size is already in place.
	Get StepKind = iota
	// Refresh replaces the local copy with the server's newer one.
	Refresh
	// Keep records the rev of a newer copy of a track deleted here: a track
	// deleted here is not fetched again.
	Keep
)

// Step is one listed track to act on.
type Step struct {
	Kind StepKind
	File track.File // as listed
	Dest string     // the local file
	// NeedTags asks for the local copy's tags before a Refresh replaces it:
	// it was fetched before tags were remembered, so its tags are the ones
	// Rekordbox has. Not when a newer copy is waiting already: Rekordbox has
	// not seen that one.
	NeedTags bool
	Err      error // the listed path is unsafe: report it, do nothing else
}

// Restore is a tombstoned track the server lists again.
type Restore struct {
	ID   string
	Path string // the server path it was fetched from
	// Refetch is set when its local file went to the recycle bin and the DJ
	// has not put it back: it is fetched again (it is then among the Gets).
	Refetch bool
}

// Recycle is a removed track whose local file the option "Delete the local
// file too" sends to the recycle bin.
type Recycle struct {
	ID   string
	Path string // the server path, for the report
	Dest string // the local file
	Gone bool   // nothing to move: the DJ deleted it already
}

// FetchPlan is what a fetch does with one listing (docs/design/library.md,
// 4.6.1). Fetch carries it out and records each outcome.
type FetchPlan struct {
	Offered    int                  // listed tracks this computer can import
	Skipped    map[string]int       // extension -> listed files it cannot import
	Restored   []Restore            // sorted by path
	Tombstones map[string]Tombstone // audio id -> a tombstone to record
	Recycle    []Recycle
	Steps      []Step // in listing order
}

// Plan says what to do with listing l, for tracks that land in folder.
// wanted tells the tracks Rekordbox can import from the others: the server
// keeps listing those so its Library view stays complete, but downloading
// them would only fill the disk (#31). recycle is the option "Delete the
// local file too".
//
// Plan first brings the state in line with the listing's protocol (begin)
// and keeps its count of skipped files; it changes nothing else.
func (s *Fetched) Plan(l track.Listing, folder string, wanted func(path string) bool,
	recycle bool, now time.Time) FetchPlan {
	s.begin(l, folder)
	p := FetchPlan{Skipped: map[string]int{}, Tombstones: map[string]Tombstone{}}
	refetch := s.planTombstones(l, folder, recycle, now, &p)

	has := func(f track.File) bool { return s.Has(f) && !(f.ID != "" && refetch[f.ID]) }
	planned := map[string]bool{} // audio ids with a step: a track listed twice is done once
	for _, f := range l.Files {
		if !wanted(f.Path) {
			p.Skipped[strings.ToLower(path.Ext(f.Path))]++
			continue
		}
		p.Offered++
		known := has(f)
		if known && !s.newer(f) {
			continue
		}
		if f.ID != "" {
			if planned[f.ID] {
				continue
			}
			planned[f.ID] = true
		}
		step := Step{Kind: Get, File: f}
		at := f.Path
		if known {
			held := s.Tracks[f.ID]
			at = held.Path
			step.Kind = Refresh
			step.NeedTags = held.Tags == nil && !held.Pending
		}
		step.Dest, step.Err = track.Local(folder, at)
		if step.Err == nil && known && !regular(step.Dest) {
			step.Kind = Keep
		}
		p.Steps = append(p.Steps, step)
	}
	s.Skipped = p.Skipped
	return p
}

// planTombstones finds the listing's removed tracks that this computer
// holds, the tombstones the server lists again, and the local files to send
// to the recycle bin. It returns the restored ids to fetch again.
func (s *Fetched) planTombstones(l track.Listing, folder string, recycle bool, now time.Time,
	p *FetchPlan) map[string]bool {
	refetch := map[string]bool{}
	if !l.ByID() {
		return refetch
	}
	listed := map[string]bool{}
	paths := map[string]bool{}
	for _, f := range l.Files {
		paths[f.Path] = true
		if f.ID != "" {
			listed[f.ID] = true
		}
	}

	// Restored on the server: listed again. A path the server lists under
	// another id counts too: the file was replaced, so the track at that
	// path is not gone and must not stay in the "removed" playlist.
	for id, tomb := range s.Removed {
		if !listed[id] && !paths[tomb.Path] {
			continue
		}
		r := Restore{ID: id, Path: tomb.Path}
		// The file went to the recycle bin because of the delete: fetch it
		// again, unless the DJ has put it back already.
		if tomb.Recycled {
			if dest, err := track.Local(folder, tomb.Path); err == nil && !exists(dest) {
				r.Refetch, refetch[id] = true, true
			}
		}
		p.Restored = append(p.Restored, r)
	}
	sort.Slice(p.Restored, func(i, j int) bool { return p.Restored[i].Path < p.Restored[j].Path })

	for _, r := range l.Removed {
		if r.ID == "" || listed[r.ID] {
			continue
		}
		if _, done := s.Removed[r.ID]; done {
			continue
		}
		// Only tracks this computer fetched: by id, or by path from before
		// link protocol 2. Anything else never reached Rekordbox from here.
		serverPath := ""
		if t, ok := s.Tracks[r.ID]; ok {
			serverPath = t.Path
		} else if _, ok := s.Legacy[r.Path]; ok {
			serverPath = r.Path
		}
		if serverPath == "" || paths[serverPath] {
			continue
		}
		// Only a track deleted in GetSetMix. A file that vanished from the
		// server's disk was nobody's decision, and this copy may be the last.
		p.Tombstones[r.ID] = Tombstone{Path: serverPath, At: now, Reason: r.Reason,
			Recycle: recycle && r.Reason == "deleted"}
	}

	// "Delete the local file too": to the recycle bin, never a hard delete,
	// tried again on the next fetch when it fails (a deck has the file loaded).
	restored := map[string]bool{}
	for _, r := range p.Restored {
		restored[r.ID] = true
	}
	consider := func(id string, tomb Tombstone) {
		if !tomb.Recycle || restored[id] {
			return
		}
		dest, err := track.Local(folder, tomb.Path)
		p.Recycle = append(p.Recycle, Recycle{ID: id, Path: tomb.Path, Dest: dest,
			Gone: err != nil || !isFile(dest)})
	}
	for id, tomb := range s.Removed {
		consider(id, tomb)
	}
	for id, tomb := range p.Tombstones {
		consider(id, tomb)
	}
	sort.Slice(p.Recycle, func(i, j int) bool { return p.Recycle[i].Dest < p.Recycle[j].Dest })
	return refetch
}

// The record calls a fetch makes, one per outcome.

// Restored drops the tombstone of a track the server lists again; one to
// fetch again is forgotten, so it is.
func (s *Fetched) Restored(r Restore) {
	delete(s.Removed, r.ID)
	if r.Refetch {
		delete(s.Tracks, r.ID)
	}
}

// Tombstoned records a tombstone of the plan.
func (s *Fetched) Tombstoned(id string, t Tombstone) { s.Removed[id] = t }

// Recycled records that a removed track's local file needs no more trying:
// it went to the recycle bin (moved), or it was gone already.
func (s *Fetched) Recycled(id string, moved bool) {
	if t, ok := s.Removed[id]; ok {
		t.Recycle = false
		t.Recycled = t.Recycled || moved
		s.Removed[id] = t
	}
}

// Got records a Get step done: f is on this computer now, holding tags
// (nil when they could not be read).
func (s *Fetched) Got(f track.File, now time.Time, tags *track.Tags) {
	s.Record(f, now)
	if tags != nil && f.ID != "" {
		s.remember(f.ID, *tags)
	}
}

// Refreshed records a Refresh step done: the newer copy is in place and
// waits for the importer. was is the old copy's tags when the step asked
// for them (nil otherwise, or when they could not be read).
func (s *Fetched) Refreshed(f track.File, now time.Time, was *track.Tags) {
	held := s.Tracks[f.ID]
	if was != nil && held.Tags == nil && !held.Pending {
		held.Tags = was
	}
	held.Rev, held.At, held.Pending = f.Rev, now, true
	s.Tracks[f.ID] = held
}

// Kept records a Keep step: the newer rev is known, nothing was fetched.
func (s *Fetched) Kept(f track.File) {
	held := s.Tracks[f.ID]
	held.Rev = f.Rev
	s.Tracks[f.ID] = held
}

func exists(path string) bool {
	_, err := os.Lstat(path)
	return err == nil
}

func isFile(path string) bool {
	info, err := os.Lstat(path)
	return err == nil && info.Mode().IsRegular()
}

// regular reports whether path is a regular file, following a link: a
// track whose local copy is a link to it is still here.
func regular(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}
