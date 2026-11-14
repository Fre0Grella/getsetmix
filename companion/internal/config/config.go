// Package config holds the companion's settings and its memory of which
// files it has already dealt with.
package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/fetch"
	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
)

// Config is the user's setup, written by `gsm-companion setup`.
type Config struct {
	// Folders are watched recursively; normally the one folder your sync
	// client (Nextcloud, Syncthing…) fills with GetSetMix downloads.
	Folders []string `json:"folders"`
	// Playlist is the root-level playlist new tracks are appended to.
	Playlist string `json:"playlist"`
	// RekordboxDir overrides where master.db lives (auto-detected if empty).
	RekordboxDir string `json:"rekordbox_dir,omitempty"`
	// RekordboxExe overrides the program `launch` starts (auto-detected if empty).
	RekordboxExe string `json:"rekordbox_exe,omitempty"`
	// Server, when set, is where `fetch` downloads new tracks from (into
	// Server.Folder, which is also watched). Without it the folders are
	// expected to be filled by a sync client.
	Server *fetch.Server `json:"server,omitempty"`
}

// DefaultPlaylist is where imports land unless configured otherwise.
const DefaultPlaylist = "GetSetMix"

// Dir is the companion's own folder: %APPDATA%\GetSetMix on Windows,
// ~/Library/Application Support/GetSetMix on macOS.
func Dir() (string, error) {
	if d := os.Getenv("GSM_COMPANION_HOME"); d != "" {
		return d, nil
	}
	base, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(base, "GetSetMix"), nil
}

// ErrNotSetUp means `gsm-companion setup` has not been run yet.
var ErrNotSetUp = errors.New("not set up yet: run `gsm-companion setup` first")

// Load reads the config from dir.
func Load(dir string) (Config, error) {
	var c Config
	data, err := os.ReadFile(filepath.Join(dir, "companion.json"))
	if errors.Is(err, os.ErrNotExist) {
		return c, ErrNotSetUp
	}
	if err != nil {
		return c, err
	}
	if err := json.Unmarshal(data, &c); err != nil {
		return c, err
	}
	if c.Playlist == "" {
		c.Playlist = DefaultPlaylist
	}
	if len(c.Folders) == 0 {
		return c, ErrNotSetUp
	}
	return c, nil
}

// Save writes the config to dir.
func (c Config) Save(dir string) error {
	return writeJSON(filepath.Join(dir, "companion.json"), c)
}

// State remembers every file the companion has handled — imported, or found
// already in the collection — so a track you delete from Rekordbox stays
// deleted instead of being re-imported on the next run.
type State struct {
	Baseline time.Time          `json:"baseline"`
	Seen     map[string]Handled `json:"seen"` // library.PathKey -> how it was when handled
	// Removed holds the tracks the importer listed in the "removed on server"
	// playlist, by library.PathKey, so none is listed twice and a restore
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

// LoadState reads the state from dir; a missing file is an empty state.
func LoadState(dir string) (*State, error) {
	s := &State{Seen: map[string]Handled{}, Removed: map[string]Listed{}}
	data, err := os.ReadFile(filepath.Join(dir, "state.json"))
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

// Save writes the state to dir.
func (s *State) Save(dir string) error {
	return writeJSON(filepath.Join(dir, "state.json"), s)
}

// Mark records files as handled, as they are now.
func (s *State) Mark(now time.Time, files ...scan.File) {
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
func (s *State) Widen(files []scan.File) bool {
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

func writeJSON(path string, v any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, append(data, '\n'), 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}
