package ledger

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/atomicfile"
	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
)

const syncedFile = "state.json"

// Synced is state.json: every file the companion has handled — imported, or found
// already in the collection — so a track you delete from Rekordbox stays
// deleted instead of being re-imported on the next run.
type Synced struct {
	Baseline time.Time          `json:"baseline"`
	Seen     map[string]Handled `json:"seen"` // track.PathKey -> how it was when handled
	// Removed holds the tracks the importer listed in the "removed on server"
	// playlist, by track.PathKey, so none is listed twice and a restore
	// can take it out again (docs/design/library.md, 4.6).
	Removed map[string]Listed `json:"removed,omitempty"`
}

// Listed is a track listed in the "removed on server" playlist.
type Listed struct {
	Path string    `json:"path"` // the local path
	At   time.Time `json:"at"`
}

// Handled is one file the companion has handled: when, and the size and
// modification time the file had then, so a later change to it can be told
// (docs/design/library.md, 3.6). A state written before link protocol 2
// holds the time alone; Size and MTime are then zero until Widen fills them.
type Handled struct {
	At    time.Time `json:"at"`
	Size  int64     `json:"size,omitempty"`
	MTime int64     `json:"mtime,omitempty"` // Unix nanoseconds
}

// UnmarshalJSON also reads the old form of a value: the time alone.
func (h *Handled) UnmarshalJSON(data []byte) error {
	if len(data) > 0 && data[0] == '"' {
		*h = Handled{}
		return json.Unmarshal(data, &h.At)
	}
	type plain Handled
	return json.Unmarshal(data, (*plain)(h))
}

// Widened reports whether the size and time of the file are known.
func (h Handled) Widened() bool { return h.Size > 0 }

// loadSynced reads state.json from dir; a missing file is an empty state.
func loadSynced(dir string) (*Synced, error) {
	s := &Synced{Seen: map[string]Handled{}, Removed: map[string]Listed{}}
	data, err := os.ReadFile(filepath.Join(dir, syncedFile))
	if errors.Is(err, os.ErrNotExist) {
		return s, nil
	}
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(data, s); err != nil {
		return nil, err
	}
	if s.Seen == nil {
		s.Seen = map[string]Handled{}
	}
	if s.Removed == nil {
		s.Removed = map[string]Listed{}
	}
	return s, nil
}

// save writes state.json to dir.
func (s *Synced) save(dir string) error {
	return atomicfile.WriteJSON(filepath.Join(dir, syncedFile), s)
}

// Mark records files as handled, as they are now.
func (s *Synced) Mark(now time.Time, files ...scan.File) {
	for _, f := range files {
		h := Handled{At: now, Size: f.Size}
		if !f.ModTime.IsZero() {
			h.MTime = f.ModTime.UnixNano()
		}
		s.Seen[f.Key] = h
	}
}

// Widen gives every handled file of files that lacks them the size and time
// it has now, keeping when it was handled; nothing else changes. Reports
// whether anything was widened.
func (s *Synced) Widen(files []scan.File) bool {
	widened := false
	for _, f := range files {
		h, ok := s.Seen[f.Key]
		if !ok || h.Widened() {
			continue
		}
		h.Size, h.MTime = f.Size, f.ModTime.UnixNano()
		s.Seen[f.Key] = h
		widened = true
	}
	return widened
}
