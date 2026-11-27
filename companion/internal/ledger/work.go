package ledger

import (
	"sort"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

// Item is one server track as a sync sees it: its audio id, and where it is
// on this computer. The importer hands items back to the record calls and
// never builds a key itself.
type Item struct {
	ID   string // the audio id; "" when state.json does not know it (Restored)
	Path string // the local path
	Key  string // track.PathKey(Path)
	// Was holds the six tag fields as this computer last saw them, for a
	// Changed item; nil when not known.
	Was *track.Tags
}

// Work is what a sync has to do about the server's tracks
// (docs/design/library.md, 4.6.1).
type Work struct {
	// Changed are tracks whose newer copy fetch put in place and whose row
	// in Rekordbox is behind, by path key.
	Changed map[string]Item
	// Removed are tracks the server removed that are not listed in the
	// "removed on server" playlist yet; Restored are listed tracks the
	// server has again. Both sorted by path.
	Removed  []Item
	Restored []Item
}

// WorkFor answers the three questions of a sync from fetched (nil without a
// paired server) and synced, for server tracks that land in folder.
//
// A track with a tombstone is never Changed: the server no longer has it.
// When a server path was replaced by other audio, two ids share the local
// file and only the newest one speaks for it.
func WorkFor(fetched *Fetched, synced *Synced, folder string) Work {
	w := Work{Changed: map[string]Item{}}
	if fetched == nil {
		return w
	}
	newest := map[string]string{} // path key -> audio id
	local := map[string]string{}  // path key -> local path
	for id, t := range fetched.Tracks {
		p, err := track.Local(folder, t.Path)
		if err != nil {
			continue
		}
		key := track.PathKey(p)
		cur, seen := newest[key]
		if !seen || t.Rev > fetched.Tracks[cur].Rev || (t.Rev == fetched.Tracks[cur].Rev && id > cur) {
			newest[key], local[key] = id, p
		}
	}
	for key, id := range newest {
		if _, removed := fetched.Removed[id]; fetched.Tracks[id].Pending && !removed {
			w.Changed[key] = Item{ID: id, Path: local[key], Key: key, Was: fetched.Tracks[id].Tags}
		}
	}

	tombstoned := map[string]Item{} // path key -> the track
	for id, tomb := range fetched.Removed {
		p, err := track.Local(folder, tomb.Path)
		if err != nil {
			continue
		}
		key := track.PathKey(p)
		tombstoned[key] = Item{ID: id, Path: p, Key: key}
	}
	for key, it := range tombstoned {
		if _, listed := synced.Removed[key]; !listed {
			w.Removed = append(w.Removed, it)
		}
	}
	for key, l := range synced.Removed {
		if _, still := tombstoned[key]; !still {
			w.Restored = append(w.Restored, Item{Path: l.Path, Key: key})
		}
	}
	byPath := func(items []Item) {
		sort.Slice(items, func(i, j int) bool { return items[i].Path < items[j].Path })
	}
	byPath(w.Removed)
	byPath(w.Restored)
	return w
}

// Unhandled are the files of files that no sync has handled yet.
func (s *Synced) Unhandled(files []scan.File) []scan.File {
	var out []scan.File
	for _, f := range files {
		if _, done := s.Seen[f.Key]; !done {
			out = append(out, f)
		}
	}
	return out
}

// Handled records files as dealt with, as they are now: imported, found in
// the collection already, or updated.
func (s *Synced) Handled(now time.Time, files ...scan.File) {
	for _, f := range files {
		h := Handled{At: now, Size: f.Size}
		if !f.ModTime.IsZero() {
			h.MTime = f.ModTime.UnixNano()
		}
		s.Seen[f.Key] = h
	}
}

// Listed records items as listed in the "removed on server" playlist, so
// none is listed twice and a restore can take it out again. A track with no
// row in the collection is recorded too: the DJ removed it from Rekordbox,
// and looking for it on every sync would open master.db for nothing.
func (s *Synced) Listed(now time.Time, items ...Item) {
	if s.Removed == nil {
		s.Removed = map[string]Listed{}
	}
	for _, it := range items {
		s.Removed[it.Key] = Listed{Path: it.Path, At: now}
	}
}

// Unlisted records items as no longer in that playlist.
func (s *Synced) Unlisted(items ...Item) {
	for _, it := range items {
		delete(s.Removed, it.Key)
	}
}

// NewSynced is a state.json that has handled nothing yet, as of baseline.
func NewSynced(baseline time.Time) *Synced {
	return &Synced{Baseline: baseline, Seen: map[string]Handled{}, Removed: map[string]Listed{}}
}

// Applied records that the Rekordbox row of a Changed item now holds tags:
// they are the ones seen from here on, and nothing waits any more.
func (s *Fetched) Applied(it Item, tags track.Tags) {
	s.Remember(it.ID, tags)
}
