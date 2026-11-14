package importer

import (
	"sort"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/fetch"
	"github.com/Fre0Grella/getsetmix/companion/internal/library"
)

// removals is what the "removed on server" playlist needs: local paths to
// list in it and paths to take out of it (docs/design/library.md, 4.6).
type removals struct {
	add  []string
	drop []string
}

func (r removals) empty() bool { return len(r.add) == 0 && len(r.drop) == 0 }

// removals compares the tombstones fetch has handled (fetched.json, read
// only: fetch owns that file) with the tracks this importer has listed
// (state.json). A tombstone not listed yet is added; a listed track whose
// tombstone is gone was restored on the server and is taken out. Without a
// paired server there are no tombstones and nothing changes: the "handled
// file is gone" rule of local mode is a later slice.
func (im *Importer) removals(state *config.State) (removals, error) {
	var r removals
	if im.Config.Server == nil || im.Config.Server.Folder == "" {
		return r, nil
	}
	fetched, err := fetch.LoadState(im.Home)
	if err != nil {
		return r, err
	}
	want := map[string]string{} // PathKey -> local path
	for _, tomb := range fetched.Removed {
		local, err := fetch.Local(im.Config.Server.Folder, tomb.Path)
		if err != nil {
			continue
		}
		want[library.PathKey(local)] = local
	}
	for key, local := range want {
		if _, done := state.Removed[key]; !done {
			r.add = append(r.add, local)
		}
	}
	for key, listed := range state.Removed {
		if _, still := want[key]; !still {
			r.drop = append(r.drop, listed.Path)
		}
	}
	sort.Strings(r.add)
	sort.Strings(r.drop)
	return r, nil
}

// record notes in state what a successful write did. A track with no row in
// the collection is recorded too: the DJ removed it from Rekordbox, and
// looking for it on every sync would open master.db for nothing.
func (r removals) record(state *config.State, now time.Time) {
	if state.Removed == nil {
		state.Removed = map[string]config.Listed{}
	}
	for _, p := range r.add {
		state.Removed[library.PathKey(p)] = config.Listed{Path: p, At: now}
	}
	for _, p := range r.drop {
		delete(state.Removed, library.PathKey(p))
	}
}
