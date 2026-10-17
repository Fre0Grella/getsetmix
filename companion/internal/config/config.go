// Package config holds the companion's settings and its memory of which
// files it has already dealt with.
package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"time"
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
	Baseline time.Time            `json:"baseline"`
	Seen     map[string]time.Time `json:"seen"` // library.PathKey -> when handled
}

// LoadState reads the state from dir; a missing file is an empty state.
func LoadState(dir string) (*State, error) {
	s := &State{Seen: map[string]time.Time{}}
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
		s.Seen = map[string]time.Time{}
	}
	return s, nil
}

// Save writes the state to dir.
func (s *State) Save(dir string) error {
	return writeJSON(filepath.Join(dir, "state.json"), s)
}

// Mark records keys as handled.
func (s *State) Mark(now time.Time, keys ...string) {
	for _, k := range keys {
		s.Seen[k] = now
	}
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
