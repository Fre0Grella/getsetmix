// Package install wires the companion into the desktop so it runs without
// anyone thinking about it:
//
//   - a "Rekordbox (GetSetMix)" launcher that imports new tracks and then
//     starts Rekordbox — the default, and nothing stays running;
//   - optionally, an autostart entry for unattended imports (Windows: a
//     resident watcher that sleeps on folder notifications; macOS: a launchd
//     agent that launchd itself starts when the folder changes).
package install

import (
	"os"
	"path/filepath"
)

// LauncherName is what the launcher shortcut is called.
const LauncherName = "Rekordbox (GetSetMix)"

// Options for Install.
type Options struct {
	Exe          string   // this program
	RekordboxExe string   // for the launcher's icon
	Folders      []string // watched folders (macOS autostart triggers on them)
	Autostart    bool
}

// Result lists what Install created, for the user.
type Result struct {
	Created []string
	Notes   []string
}

// Self is the absolute path of the running executable.
func Self() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	return filepath.EvalSymlinks(exe)
}
