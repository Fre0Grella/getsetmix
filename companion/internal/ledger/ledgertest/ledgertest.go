// Package ledgertest prepares the ledger's files for tests the way the
// companion writes them: under the file's lock.
package ledgertest

import (
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/ledger"
)

// Save writes state (a *ledger.Fetched or a *ledger.Synced) into dir.
func Save(t testing.TB, dir string, state any) {
	t.Helper()
	var err error
	switch s := state.(type) {
	case *ledger.Fetched:
		var l *ledger.FetchLock
		if l, err = ledger.LockFetch(dir); err == nil {
			err = l.Save(s)
			l.Unlock()
		}
	case *ledger.Synced:
		var l *ledger.SyncLock
		if l, err = ledger.LockSync(dir, time.Second); err == nil {
			err = l.Save(s)
			l.Unlock()
		}
	default:
		t.Fatalf("ledgertest.Save: %T is no ledger state", state)
	}
	if err != nil {
		t.Fatal(err)
	}
}
