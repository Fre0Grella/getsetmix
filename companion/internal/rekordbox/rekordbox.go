// Package rekordbox knows where Rekordbox lives on this machine and whether
// it is running — the one thing that decides when master.db may be written.
package rekordbox

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Install is a Rekordbox installation.
type Install struct {
	Dir string // holds master.db and masterPlaylists6.xml
	Exe string // program to start; empty when not found
}

// DB is the collection database.
func (i Install) DB() string { return filepath.Join(i.Dir, "master.db") }

// PlaylistXML is the playlist mirror Rekordbox keeps beside master.db.
func (i Install) PlaylistXML() string { return filepath.Join(i.Dir, "masterPlaylists6.xml") }

// ErrNotFound means no Rekordbox 6/7 library exists on this machine.
var ErrNotFound = errors.New("no Rekordbox 6/7 library found (master.db)")

// Locate finds the library and the executable, honouring overrides.
func Locate(dirOverride, exeOverride string) (Install, error) {
	inst := Install{Dir: dirOverride, Exe: exeOverride}
	if inst.Dir == "" {
		inst.Dir = agentDBDir(pioneerAppDir())
	}
	if inst.Dir == "" {
		inst.Dir = filepath.Join(pioneerAppDir(), "rekordbox")
	}
	if inst.Exe == "" {
		inst.Exe = findExe()
	}
	if _, err := os.Stat(inst.DB()); err != nil {
		return inst, ErrNotFound
	}
	return inst, nil
}

// agentDBDir reads where Rekordbox keeps master.db from its agent's
// options.json ({"options": [["db-path", "…/master.db"], …]}): the database
// can be moved away from the default folder.
func agentDBDir(pioneer string) string {
	data, err := os.ReadFile(filepath.Join(pioneer, "rekordboxAgent", "storage", "options.json"))
	if err != nil {
		return ""
	}
	var opts struct {
		Options [][]any `json:"options"`
	}
	if json.Unmarshal(data, &opts) != nil {
		return ""
	}
	for _, kv := range opts.Options {
		if len(kv) == 2 && kv[0] == "db-path" {
			if p, ok := kv[1].(string); ok && p != "" {
				return filepath.Dir(p)
			}
		}
	}
	return ""
}

// IsRunning reports whether Rekordbox is open right now.
func IsRunning() (bool, error) {
	pids, err := Running()
	return len(pids) > 0, err
}

// WaitClosed blocks until Rekordbox is not running (or ctx ends). It sleeps
// on the OS's process-exit notification, so a waiting companion costs no CPU.
func WaitClosed(ctx context.Context) error {
	for {
		pids, err := Running()
		if err != nil {
			return err
		}
		if len(pids) == 0 {
			return nil
		}
		if err := waitExit(ctx, pids); err != nil {
			return err
		}
		// Rekordbox finishes writing master.db a moment after it exits.
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(2 * time.Second):
		}
	}
}

// newest picks the highest-versioned candidate; versionOf extracts the
// version from a path ("…/rekordbox 7.2.19/…" -> "7.2.19").
func newest(candidates []string, versionOf func(string) string) string {
	if len(candidates) == 0 {
		return ""
	}
	sort.Slice(candidates, func(i, j int) bool {
		return versionLess(versionOf(candidates[j]), versionOf(candidates[i]))
	})
	return candidates[0]
}

func versionLess(a, b string) bool {
	pa, pb := strings.Split(a, "."), strings.Split(b, ".")
	for i := 0; i < len(pa) || i < len(pb); i++ {
		var x, y int
		if i < len(pa) {
			x, _ = strconv.Atoi(pa[i])
		}
		if i < len(pb) {
			y, _ = strconv.Atoi(pb[i])
		}
		if x != y {
			return x < y
		}
	}
	return false
}

// folderVersion reads the version from the folder a program sits in.
func folderVersion(path string) string {
	f := strings.Fields(filepath.Base(filepath.Dir(path)))
	if len(f) == 0 {
		return ""
	}
	return f[len(f)-1]
}
