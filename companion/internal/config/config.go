// Package config holds the companion's settings: companion.json. What the
// companion remembers between syncs is the ledger's (internal/ledger).
package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"

	"github.com/Fre0Grella/getsetmix/companion/internal/atomicfile"
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
	Server *Server `json:"server,omitempty"`
}

// Server is where tracks come from: written by the setup when it pairs this
// computer.
type Server struct {
	URL   string `json:"url"`   // e.g. https://getsetmix.tailnet.ts.net
	Token string `json:"token"` // this computer's link token
	// Folder receives the tracks; it is also one of the watched folders.
	Folder string `json:"folder"`
	// DeleteRemovedFiles is the option "Delete the local file too": a track
	// the server removed then goes to the system's recycle bin. Off by
	// default; the file stays.
	DeleteRemovedFiles bool `json:"delete_removed_files,omitempty"`
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
	return atomicfile.WriteJSON(filepath.Join(dir, "companion.json"), c)
}
