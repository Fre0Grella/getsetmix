package ledger

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/atomicfile"
	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

const (
	fetchedFile   = "fetched.json"
	fetchedFileV1 = "fetched.v1.json" // the version 1 file, kept when it is migrated
)

// Fetched is fetched.json: which server tracks this computer fetched
// (docs/design/library.md, 3.6).
//
// Version 1 maps a server path to when it was fetched. It stays the format
// while the server speaks link protocol 1. The first fetch against a protocol 2
// server migrates it to version 2, keyed by audio id: each listed path the
// state knows gets its id, and the paths the server no longer lists stay in
// Legacy, so they are never fetched again if they come back.
type Fetched struct {
	Version int                  // 1 or 2: what Save writes
	Tracks  map[string]Track     // audio id -> the track this computer holds
	Legacy  map[string]time.Time // server path -> when fetched, for tracks known by path only
	Removed map[string]Tombstone // audio id -> the tombstone handled (removed.go)
	// Skipped counts, by extension, the files of the last listing that
	// Rekordbox cannot import and so were not downloaded.
	Skipped map[string]int

	byID  bool            // the last listing (Begin) names tracks by audio id
	paths map[string]bool // every path in Tracks and Legacy
}

// Tombstone is a track this computer holds that the server removed: trashed
// in GetSetMix ("deleted") or gone from the server's disk ("missing")
// (docs/design/library.md, 4.6).
//
// Handling it here only records it. The importer reads the recorded
// tombstones and lists their tracks in the "GetSetMix: removed on server"
// playlist, under its own safety; nothing is removed from the collection.
// When the server lists the id again (a restore), the tombstone is dropped
// and the importer takes the track out of that playlist.
type Tombstone struct {
	Path   string    `json:"path"`             // the server path the track was fetched from
	At     time.Time `json:"at"`               // when this computer handled the tombstone
	Reason string    `json:"reason,omitempty"` // "deleted" or "missing"
	// Recycle is set while the local file still has to go to the recycle
	// bin (the option was on when the tombstone was handled, and no try has
	// worked yet); Recycled once it went.
	Recycle  bool `json:"recycle,omitempty"`
	Recycled bool `json:"recycled,omitempty"`
}

// UnmarshalJSON also reads the form the design first gave a value: the
// time alone.
func (t *Tombstone) UnmarshalJSON(data []byte) error {
	if len(data) > 0 && data[0] == '"' {
		*t = Tombstone{}
		return json.Unmarshal(data, &t.At)
	}
	type plain Tombstone
	return json.Unmarshal(data, (*plain)(t))
}

// Track is one fetched track in a version 2 state.
type Track struct {
	Path string    `json:"path"` // the server path it was fetched from
	Rev  int64     `json:"rev"`  // the rev this computer holds; 0 means older than any
	At   time.Time `json:"at"`
	// Tags are the six tag fields as this computer last saw them: read from
	// the file when it was first fetched, and kept when a newer copy replaces
	// it until the importer has written the changes to Rekordbox. Nil when not
	// known (a track fetched before tags were remembered, or a file without
	// tags).
	Tags *track.Tags `json:"tags,omitempty"`
	// Pending is set when fetch put a newer copy in place, until the importer
	// has brought the Rekordbox row in line with it.
	Pending bool `json:"pending,omitempty"`
}

// Empty reports whether the state knows no track at all: nothing fetched,
// nothing removed. Setup seeds only an empty state, never one in use.
func (s *Fetched) Empty() bool {
	return len(s.Tracks) == 0 && len(s.Legacy) == 0 && len(s.Removed) == 0
}

// Remember notes the tags this computer has seen for the track with audio id;
// whatever was waiting for the importer has been handled.
func (s *Fetched) Remember(id string, tags track.Tags) {
	if t, ok := s.Tracks[id]; ok {
		t.Tags, t.Pending = &tags, false
		s.Tracks[id] = t
	}
}

// Newer reports whether the listing holds a newer copy of a fetched track:
// its rev is above the one this computer holds.
func (s *Fetched) Newer(f track.File) bool {
	if !s.byID || f.ID == "" {
		return false
	}
	t, ok := s.Tracks[f.ID]
	return ok && f.Rev > t.Rev
}

// NewFetched is an empty state, written as version 1 until a protocol 2 server
// is seen.
func NewFetched() *Fetched {
	s := &Fetched{Version: 1}
	s.init()
	return s
}

func (s *Fetched) init() {
	if s.Version == 0 {
		s.Version = 1
	}
	if s.Tracks == nil {
		s.Tracks = map[string]Track{}
	}
	if s.Legacy == nil {
		s.Legacy = map[string]time.Time{}
	}
	if s.Removed == nil {
		s.Removed = map[string]Tombstone{}
	}
}

// Begin prepares the state for a listing. Against a protocol 2 server the
// state becomes version 2, and every listed file whose path is known by path
// only gets its audio id: with the listed rev when the local file in folder
// has the listed size, and rev 0 otherwise, so it counts as changed.
func (s *Fetched) Begin(l track.Listing, folder string) {
	s.init()
	s.byID = l.ByID()
	if s.byID {
		s.Version = 2
		for _, f := range l.Files {
			if f.ID == "" {
				continue
			}
			if _, known := s.Tracks[f.ID]; known {
				continue
			}
			at, known := s.Legacy[f.Path]
			if !known {
				continue
			}
			rev := f.Rev
			if dest, err := track.Local(folder, f.Path); err != nil || !track.HasSize(dest, f.Size) {
				rev = 0
			}
			s.Tracks[f.ID] = Track{Path: f.Path, Rev: rev, At: at}
			delete(s.Legacy, f.Path)
		}
	}
	s.paths = map[string]bool{}
	for p := range s.Legacy {
		s.paths[p] = true
	}
	for _, t := range s.Tracks {
		s.paths[t.Path] = true
	}
}

// Has reports whether f was fetched before: by audio id from a protocol 2
// server, by path from an older one.
func (s *Fetched) Has(f track.File) bool {
	if s.byID && f.ID != "" {
		_, ok := s.Tracks[f.ID]
		return ok
	}
	return s.paths[f.Path]
}

// Record notes that f is on this computer now.
func (s *Fetched) Record(f track.File, now time.Time) {
	if s.paths == nil {
		s.Begin(track.Listing{}, "")
	}
	if s.byID && f.ID != "" {
		s.Tracks[f.ID] = Track{Path: f.Path, Rev: f.Rev, At: now}
	} else {
		s.Legacy[f.Path] = now
	}
	s.paths[f.Path] = true
}

// RecordAll notes every file of l as fetched, so only tracks the server gets
// from now on are downloaded.
func (s *Fetched) RecordAll(l track.Listing, now time.Time) {
	s.Begin(l, "")
	for _, f := range l.Files {
		s.Record(f, now)
	}
}

// SkippedSummary says how many listed files this computer does not download
// and why; empty when there are none.
func (s *Fetched) SkippedSummary() string {
	total := 0
	exts := make([]string, 0, len(s.Skipped))
	for ext, n := range s.Skipped {
		total += n
		exts = append(exts, ext)
	}
	if total == 0 {
		return ""
	}
	sort.Strings(exts)
	parts := make([]string, len(exts))
	for i, ext := range exts {
		name := strings.TrimPrefix(ext, ".")
		if name == "" {
			name = "no extension"
		}
		parts[i] = fmt.Sprintf("%d %s", s.Skipped[ext], name)
	}
	return fmt.Sprintf("%d file(s) Rekordbox cannot import (%s): not downloaded, kept on the server",
		total, strings.Join(parts, ", "))
}

// stateV1 is the file as companions before link protocol 2 write it, and as
// this one writes it while the server speaks protocol 1.
type stateV1 struct {
	Fetched map[string]time.Time `json:"fetched"`
	Skipped map[string]int       `json:"skipped,omitempty"`
}

type stateV2 struct {
	Version int                  `json:"version"`
	Tracks  map[string]Track     `json:"tracks"`
	Legacy  map[string]time.Time `json:"legacy"`
	Removed map[string]Tombstone `json:"removed"`
	Skipped map[string]int       `json:"skipped,omitempty"`
}

// MarshalJSON writes the state in its version's format.
func (s *Fetched) MarshalJSON() ([]byte, error) {
	s.init()
	if s.Version < 2 {
		return json.Marshal(stateV1{Fetched: s.Legacy, Skipped: s.Skipped})
	}
	return json.Marshal(stateV2{Version: 2, Tracks: s.Tracks, Legacy: s.Legacy,
		Removed: s.Removed, Skipped: s.Skipped})
}

// UnmarshalJSON reads either version.
func (s *Fetched) UnmarshalJSON(data []byte) error {
	var raw struct {
		stateV2
		Fetched map[string]time.Time `json:"fetched"`
	}
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	*s = Fetched{Version: raw.Version, Tracks: raw.Tracks, Legacy: raw.Legacy,
		Removed: raw.Removed, Skipped: raw.Skipped}
	if raw.Version < 2 {
		*s = Fetched{Version: 1, Legacy: raw.Fetched, Skipped: raw.Skipped}
	}
	s.init()
	return nil
}

// loadFetched reads fetched.json from dir; a missing file is an empty state.
func loadFetched(dir string) (*Fetched, error) {
	data, err := os.ReadFile(filepath.Join(dir, fetchedFile))
	if errors.Is(err, os.ErrNotExist) {
		return NewFetched(), nil
	}
	if err != nil {
		return nil, err
	}
	s := &Fetched{}
	if err := json.Unmarshal(data, s); err != nil {
		return nil, err
	}
	return s, nil
}

// save writes fetched.json to dir. The first time a version 2 state
// replaces a version 1 file, the old file is kept as fetched.v1.json.
func (s *Fetched) save(dir string) error {
	if s.Version >= 2 {
		if err := keepV1(dir); err != nil {
			return err
		}
	}
	return atomicfile.WriteJSON(filepath.Join(dir, fetchedFile), s)
}

func keepV1(dir string) error {
	keep := filepath.Join(dir, fetchedFileV1)
	if _, err := os.Stat(keep); err == nil {
		return nil
	}
	old, err := os.ReadFile(filepath.Join(dir, fetchedFile))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	var v struct {
		Version int `json:"version"`
	}
	if json.Unmarshal(old, &v) != nil || v.Version >= 2 {
		return nil
	}
	return os.WriteFile(keep, old, 0o644)
}
