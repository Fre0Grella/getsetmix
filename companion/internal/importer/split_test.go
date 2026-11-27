package importer

import (
	"testing"

	"github.com/Fre0Grella/getsetmix/companion/internal/ledger"
	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
)

// The one rule sync and status share: a file never handled is new; a handled
// file is acted on only when fetch put a newer server copy in its place.
func TestSplitTellsNewFromChangedAndLeavesTheRest(t *testing.T) {
	t.Parallel()
	ready := []scan.File{{Key: "new"}, {Key: "changed"}, {Key: "done"}}
	state := &ledger.Synced{Seen: map[string]ledger.Handled{"changed": {}, "done": {}}}
	pending, changed := Split(ready, state, ledger.Work{Changed: map[string]ledger.Item{"changed": {ID: "a1_x"}, "new": {ID: "a1_y"}}})
	if len(pending) != 1 || pending[0].Key != "new" {
		t.Fatalf("pending %v", pending)
	}
	if len(changed) != 1 || changed[0].Key != "changed" {
		t.Fatalf("changed %v", changed)
	}
	if p, c := Split(ready, state, ledger.Work{}); len(p) != 1 || len(c) != 0 {
		t.Fatalf("without a fetch state: pending %v changed %v", p, c)
	}
}
