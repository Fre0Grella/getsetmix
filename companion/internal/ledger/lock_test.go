package ledger

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

// age makes the lock file in dir look last touched ago.
func age(t *testing.T, dir, name string, ago time.Duration) {
	t.Helper()
	old := time.Now().Add(-ago)
	if err := os.Chtimes(filepath.Join(dir, name), old, old); err != nil {
		t.Fatal(err)
	}
}

// fetch.lock is exclusive and refused at once, as it always was: an import
// never waits for a fetch.
func TestFetchLockIsExclusive(t *testing.T) {
	dir := t.TempDir()
	l, err := LockFetch(dir)
	if err != nil {
		t.Fatal(err)
	}
	start := time.Now()
	if _, err := LockFetch(dir); !errors.Is(err, ErrFetchRunning) {
		t.Fatalf("second lock: %v", err)
	}
	if time.Since(start) > time.Second {
		t.Fatal("a held fetch.lock was waited for")
	}
	l.Unlock()
	l.Unlock() // a second release does nothing
	again, err := LockFetch(dir)
	if err != nil {
		t.Fatal(err)
	}
	again.Unlock()
}

// A lock whose holder is gone is taken over once it is older than its limit,
// and not before.
func TestAnAbandonedLockIsTakenOver(t *testing.T) {
	dir := t.TempDir()
	if _, err := LockFetch(dir); err != nil {
		t.Fatal(err)
	}
	age(t, dir, fetchLockFile, time.Hour)
	if _, err := LockFetch(dir); !errors.Is(err, ErrFetchRunning) {
		t.Fatalf("an hour-old fetch.lock: %v", err)
	}
	age(t, dir, fetchLockFile, 3*time.Hour)
	l, err := LockFetch(dir)
	if err != nil {
		t.Fatalf("a three-hour-old fetch.lock was not taken over: %v", err)
	}
	l.Unlock()

	// What a sync that died leaves behind: the file, and nobody refreshing it.
	if err := os.WriteFile(filepath.Join(dir, syncLockFile), nil, 0o644); err != nil {
		t.Fatal(err)
	}
	age(t, dir, syncLockFile, syncLockLimit+time.Minute)
	s, err := LockSync(dir, 0)
	if err != nil {
		t.Fatalf("an abandoned sync.lock was not taken over: %v", err)
	}
	s.Unlock()
}

// A second sync gets sync.lock only once the first has ended, and gives up
// after its wait.
func TestOneSyncAtATime(t *testing.T) {
	dir := t.TempDir()
	first, err := LockSync(dir, 0)
	if err != nil {
		t.Fatal(err)
	}
	start := time.Now()
	if _, err := LockSync(dir, 300*time.Millisecond); !errors.Is(err, ErrSyncRunning) {
		t.Fatalf("while held: %v", err)
	}
	if waited := time.Since(start); waited < 300*time.Millisecond {
		t.Fatalf("gave up after %v, before its wait", waited)
	}

	released := make(chan time.Time, 1)
	go func() {
		time.Sleep(400 * time.Millisecond)
		released <- time.Now()
		first.Unlock()
	}()
	second, err := LockSync(dir, 10*time.Second)
	got := time.Now()
	if err != nil {
		t.Fatal(err)
	}
	defer second.Unlock()
	if at := <-released; got.Before(at) {
		t.Fatal("the second sync got the lock while the first held it")
	}
}

// A sync that holds the lock longer than the lock's limit keeps it: it
// refreshes the file while it runs.
func TestAHeldSyncLockStaysFresh(t *testing.T) {
	limit, beat := syncLockLimit, syncBeat
	syncLockLimit, syncBeat = 600*time.Millisecond, 50*time.Millisecond
	t.Cleanup(func() { syncLockLimit, syncBeat = limit, beat })

	dir := t.TempDir()
	l, err := LockSync(dir, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer l.Unlock()
	time.Sleep(2 * syncLockLimit)
	if _, err := LockSync(dir, 0); !errors.Is(err, ErrSyncRunning) {
		t.Fatalf("a running sync's lock was taken over: %v", err)
	}
}

// Syncs that each read, change and save state.json lose no write when they
// run at once: the lock puts them one after the other.
func TestConcurrentSyncsLoseNoWrite(t *testing.T) {
	dir := t.TempDir()
	const n = 8
	var wg sync.WaitGroup
	errs := make(chan error, n)
	for i := range n {
		wg.Add(1)
		go func() {
			defer wg.Done()
			l, err := LockSync(dir, 30*time.Second)
			if err != nil {
				errs <- err
				return
			}
			defer l.Unlock()
			s, err := l.Load()
			if err != nil {
				errs <- err
				return
			}
			s.Seen[fmt.Sprintf("file%d", i)] = Handled{At: time.Now()}
			errs <- l.Save(s)
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatal(err)
		}
	}
	s, err := ReadSynced(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(s.Seen) != n {
		t.Fatalf("%d of %d writes kept: %v", len(s.Seen), n, s.Seen)
	}
}

// A lock can be taken before the companion's folder exists (Setup's first
// run), and its file goes when it is released.
func TestLocksWorkInAFolderNotMadeYet(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "GetSetMix")
	l, err := LockSync(dir, 0)
	if err != nil {
		t.Fatal(err)
	}
	l.Unlock()
	if _, err := os.Stat(filepath.Join(dir, syncLockFile)); !os.IsNotExist(err) {
		t.Fatalf("sync.lock left behind: %v", err)
	}
}
