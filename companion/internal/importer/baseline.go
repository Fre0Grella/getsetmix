package importer

import (
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/rekordbox"
	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
)

// BaselineReport counts what Baseline found in the folders.
type BaselineReport struct {
	Files        int // tracks in the folders
	InCollection int // of which Rekordbox already has
	Outside      int // of which Rekordbox doesn't have
}

// Baseline records what the folders already hold as handled, so only tracks
// that arrive from now on are imported; with importExisting, the tracks
// Rekordbox doesn't have are left pending instead and import on the next
// sync. It replaces the companion's state, reading master.db read-only.
func Baseline(home string, inst rekordbox.Install, folders []string, importExisting bool, now time.Time) (BaselineReport, error) {
	var rep BaselineReport
	known := map[string]bool{}
	if inst.Dir != "" {
		db, err := library.OpenReadOnly(inst.DB())
		if err != nil {
			return rep, err
		}
		known, err = db.KnownPaths()
		db.Close()
		if err != nil {
			return rep, err
		}
	}
	found, err := scan.Folders(folders, now)
	if err != nil {
		return rep, err
	}
	state := &config.State{Baseline: now, Seen: map[string]time.Time{}}
	for _, f := range found.Ready {
		rep.Files++
		switch {
		case known[f.Key]:
			rep.InCollection++
			state.Mark(now, f.Key)
		case importExisting:
			rep.Outside++
		default:
			rep.Outside++
			state.Mark(now, f.Key)
		}
	}
	return rep, state.Save(home)
}
