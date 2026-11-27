package fetch

import (
	"sort"

	"github.com/Fre0Grella/getsetmix/companion/internal/ledger"
	"github.com/Fre0Grella/getsetmix/companion/internal/recycle"
)

func (c *Client) recycle(path string) error {
	if c.Recycle != nil {
		return c.Recycle(path)
	}
	return recycle.Move(path)
}

// tombstones carries out the plan's part about removed tracks: tombstones
// the server lists again are dropped, new ones recorded, and, with the
// option on, local files sent to the recycle bin, never further; a move
// that fails (a deck has the file loaded) is tried again on the next fetch.
func (c *Client) tombstones(plan ledger.FetchPlan, state *ledger.Fetched, rep *Report) {
	for _, r := range plan.Restored {
		state.Restored(r)
		rep.Restored = append(rep.Restored, r.Path)
	}
	for id, t := range plan.Tombstones {
		state.Tombstoned(id, t)
		rep.Removed = append(rep.Removed, t.Path)
	}
	for _, r := range plan.Recycle {
		if r.Gone {
			state.Recycled(r.ID, false)
			continue
		}
		if err := c.recycle(r.Dest); err != nil {
			rep.Failed[r.Path] = "not moved to the recycle bin: " + err.Error()
			continue
		}
		state.Recycled(r.ID, true)
		rep.Recycled = append(rep.Recycled, r.Dest)
	}
	sort.Strings(rep.Removed)
	sort.Strings(rep.Restored)
	sort.Strings(rep.Recycled)
}
