package fetch

import (
	"os"
	"sort"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/ledger"
	"github.com/Fre0Grella/getsetmix/companion/internal/recycle"
)

func (c *Client) recycle(path string) error {
	if c.Recycle != nil {
		return c.Recycle(path)
	}
	return recycle.Move(path)
}

// tombstones records the listing's removed tracks that this computer holds,
// drops the ones the server lists again, and, with the option on, sends the
// local files of newly removed tracks to the recycle bin.
func (c *Client) tombstones(l Listing, state *ledger.Fetched, now time.Time, rep *Report) {
	if !l.ByID() {
		return
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
	for id, tomb := range state.Removed {
		if !listed[id] && !paths[tomb.Path] {
			continue
		}
		delete(state.Removed, id)
		rep.Restored = append(rep.Restored, tomb.Path)
		// The file went to the recycle bin because of the delete: fetch it
		// again, unless the DJ has put it back already.
		if tomb.Recycled {
			if dest, err := Local(c.Server.Folder, tomb.Path); err == nil && !exists(dest) {
				delete(state.Tracks, id)
			}
		}
	}

	for _, r := range l.Removed {
		if r.ID == "" || listed[r.ID] {
			continue
		}
		if _, done := state.Removed[r.ID]; done {
			continue
		}
		// Only tracks this computer fetched: by id, or by path from before
		// link protocol 2. Anything else never reached Rekordbox from here.
		serverPath := ""
		if t, ok := state.Tracks[r.ID]; ok {
			serverPath = t.Path
		} else if _, ok := state.Legacy[r.Path]; ok {
			serverPath = r.Path
		}
		if serverPath == "" || paths[serverPath] {
			continue
		}
		// Only a track deleted in GetSetMix. A file that vanished from the
		// server's disk was nobody's decision, and this copy may be the last.
		state.Removed[r.ID] = ledger.Tombstone{Path: serverPath, At: now, Reason: r.Reason,
			Recycle: c.Server.DeleteRemovedFiles && r.Reason == "deleted"}
		rep.Removed = append(rep.Removed, serverPath)
	}

	// "Delete the local file too": to the recycle bin, never a hard delete,
	// retried on the next fetch when it fails (a deck has the file loaded).
	for id, tomb := range state.Removed {
		if !tomb.Recycle {
			continue
		}
		dest, err := Local(c.Server.Folder, tomb.Path)
		if err != nil || !isFile(dest) {
			tomb.Recycle = false // nothing to move: the DJ deleted it already
			state.Removed[id] = tomb
			continue
		}
		if err := c.recycle(dest); err != nil {
			rep.Failed[tomb.Path] = "not moved to the recycle bin: " + err.Error()
			continue
		}
		tomb.Recycle, tomb.Recycled = false, true
		state.Removed[id] = tomb
		rep.Recycled = append(rep.Recycled, dest)
	}
	sort.Strings(rep.Removed)
	sort.Strings(rep.Restored)
	sort.Strings(rep.Recycled)
}

func exists(path string) bool {
	_, err := os.Lstat(path)
	return err == nil
}

func isFile(path string) bool {
	info, err := os.Lstat(path)
	return err == nil && info.Mode().IsRegular()
}
