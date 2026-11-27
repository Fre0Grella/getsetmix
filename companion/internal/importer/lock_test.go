package importer

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/ledger"
)

// One sync at a time (docs/design/library.md, 4.6.1): a sync that finds
// another one running past its wait does nothing at all, not even a backup,
// and the next sync imports what it left.
func TestASyncWhileAnotherRunsIsSkipped(t *testing.T) {
	wait := syncWait
	syncWait = 200 * time.Millisecond
	t.Cleanup(func() { syncWait = wait })

	e := newEnv(t)
	e.add(t, "new one.mp3")
	other, err := ledger.LockSync(e.im.Home, 0)
	if err != nil {
		t.Fatal(err)
	}
	rep, err := e.im.Sync(false)
	if !errors.Is(err, ErrSyncRunning) || len(rep.Imported) != 0 {
		t.Fatalf("%+v, %v", rep, err)
	}
	if n := e.count(t, "SELECT count(*) FROM djmdContent"); n != 1 {
		t.Fatalf("%d rows: the skipped sync imported", n)
	}
	for _, name := range []string{"state.json", "backup"} {
		if _, err := os.Stat(filepath.Join(e.im.Home, name)); !os.IsNotExist(err) {
			t.Errorf("the skipped sync wrote %s", name)
		}
	}

	other.Unlock()
	if rep, err := e.im.Sync(false); err != nil || len(rep.Imported) != 1 {
		t.Fatalf("the next sync: %+v, %v", rep, err)
	}
}

// A dry run reads only, so it runs while a sync holds the lock.
func TestADryRunTakesNoLock(t *testing.T) {
	e := newEnv(t)
	e.add(t, "new one.mp3")
	other, err := ledger.LockSync(e.im.Home, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer other.Unlock()
	if rep, err := e.im.Sync(true); err != nil || len(rep.Imported) != 1 {
		t.Fatalf("%+v, %v", rep, err)
	}
}
