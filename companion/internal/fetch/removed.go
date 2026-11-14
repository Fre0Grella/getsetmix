package fetch

import (
	"encoding/json"
	"os"
	"sort"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/recycle"
)

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

func (c *Client) recycle(path string) error {
	if c.Recycle != nil {
		return c.Recycle(path)
	}
	return recycle.Move(path)
}

// tombstones records the listing's removed tracks that this computer holds,
// drops the ones the server lists again, and, with the option on, sends the
// local files of newly removed tracks to the recycle bin.
func (c *Client) tombstones(l Listing, state *State, now time.Time, rep *Report) {
	if !l.ByID() {
		return
	}
	listed := map[string]bool{}
	for _, f := range l.Files {
		if f.ID != "" {
			listed[f.ID] = true
		}
	}

	// Restored on the server: listed again.
	for id, tomb := range state.Removed {
		if !listed[id] {
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
		if serverPath == "" {
			continue
		}
		state.Removed[r.ID] = Tombstone{Path: serverPath, At: now, Reason: r.Reason,
			Recycle: c.Server.DeleteRemovedFiles}
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
