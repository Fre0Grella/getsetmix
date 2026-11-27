package importer

import "github.com/Fre0Grella/getsetmix/companion/internal/ledger"

// removals is what the "removed on server" playlist needs: local paths to
// list in it and paths to take out of it (docs/design/library.md, 4.6).
type removals struct {
	add  []string
	drop []string
}

func (r removals) empty() bool { return len(r.add) == 0 && len(r.drop) == 0 }

// marksOf is the playlist's part of a sync's work: tracks the server removed
// that are not listed yet, and listed tracks the server has again. Without a
// paired server there are none: the "handled file is gone" rule of local
// mode is a later slice.
func marksOf(w ledger.Work) removals {
	var r removals
	for _, it := range w.Removed {
		r.add = append(r.add, it.Path)
	}
	for _, it := range w.Restored {
		r.drop = append(r.drop, it.Path)
	}
	return r
}
