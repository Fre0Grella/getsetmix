package ledger

import (
	"errors"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// The two locks (docs/design/library.md, 4.6.1). fetch.lock means a fetch is
// running or fetched.json is being changed; sync.lock means an import into
// Rekordbox is running, and covers state.json and the backup folder. Taken
// in that order only: sync.lock first, then fetch.lock, which an import only
// tries. A fetch never waits for sync.lock while it holds fetch.lock, so the
// two cannot deadlock.
const (
	fetchLockFile = "fetch.lock"
	syncLockFile  = "sync.lock"
)

var (
	// ErrFetchRunning means another process holds fetch.lock.
	ErrFetchRunning = errors.New("another fetch is running")
	// ErrSyncRunning means another sync held sync.lock for longer than the
	// wait.
	ErrSyncRunning = errors.New("another sync is running")
)

// A holder that is gone leaves its lock file behind; after these ages the
// lock is taken over. fetch.lock keeps the limit companions have always
// used, since an older companion may hold it for a long fetch. sync.lock is
// new: its holder refreshes it every syncBeat, so a short limit is safe.
// Variables so tests can shorten them.
var (
	fetchLockLimit = 2 * time.Hour
	syncLockLimit  = 5 * time.Minute
	syncBeat       = time.Minute
	syncRetry      = 250 * time.Millisecond
)

// take creates the lock file at path, taking over one older than limit.
// false means another holder has it.
func take(path string, limit time.Duration) (bool, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return false, err
	}
	for range 2 {
		f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
		if err == nil {
			return true, f.Close()
		}
		if !errors.Is(err, os.ErrExist) {
			return false, err
		}
		info, serr := os.Stat(path)
		if serr != nil || time.Since(info.ModTime()) <= limit {
			break
		}
		_ = os.Remove(path) // its holder is gone
	}
	return false, nil
}

// FetchLock is fetch.lock, held. Only through it can fetched.json be read
// for a change and written.
type FetchLock struct {
	dir  string
	once sync.Once
}

// LockFetch takes fetch.lock in dir, or returns ErrFetchRunning at once when
// another process holds it.
func LockFetch(dir string) (*FetchLock, error) {
	ok, err := take(filepath.Join(dir, fetchLockFile), fetchLockLimit)
	if err != nil {
		return nil, err
	}
	if !ok {
		return nil, ErrFetchRunning
	}
	return &FetchLock{dir: dir}, nil
}

// Load reads fetched.json, under the lock.
func (l *FetchLock) Load() (*Fetched, error) { return loadFetched(l.dir) }

// Save writes fetched.json, under the lock.
func (l *FetchLock) Save(s *Fetched) error { return s.save(l.dir) }

// Unlock releases fetch.lock; later calls do nothing.
func (l *FetchLock) Unlock() {
	l.once.Do(func() { _ = os.Remove(filepath.Join(l.dir, fetchLockFile)) })
}

// ReadFetched is fetched.json as it is now, for a question only (status, or
// whether a sync has anything to do): no lock, since the file is replaced by
// a rename and a snapshot is always whole. Never save what it returns.
func ReadFetched(dir string) (*Fetched, error) { return loadFetched(dir) }

// SyncLock is sync.lock, held: one sync at a time. Only through it can
// state.json be read for a change and written.
type SyncLock struct {
	dir  string
	stop chan struct{}
	once sync.Once
}

// LockSync takes sync.lock in dir, waiting up to wait for a sync that holds
// it to end; then it returns ErrSyncRunning. While held, the lock file is
// refreshed so it never looks abandoned.
func LockSync(dir string, wait time.Duration) (*SyncLock, error) {
	path := filepath.Join(dir, syncLockFile)
	deadline := time.Now().Add(wait)
	for {
		ok, err := take(path, syncLockLimit)
		if err != nil {
			return nil, err
		}
		if ok {
			break
		}
		if !time.Now().Before(deadline) {
			return nil, ErrSyncRunning
		}
		time.Sleep(min(syncRetry, time.Until(deadline)))
	}
	l := &SyncLock{dir: dir, stop: make(chan struct{})}
	go l.beat(path, syncBeat)
	return l, nil
}

func (l *SyncLock) beat(path string, every time.Duration) {
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		select {
		case <-l.stop:
			return
		case now := <-t.C:
			_ = os.Chtimes(path, now, now)
		}
	}
}

// Load reads state.json, under the lock.
func (l *SyncLock) Load() (*Synced, error) { return loadSynced(l.dir) }

// Save writes state.json, under the lock.
func (l *SyncLock) Save(s *Synced) error { return s.save(l.dir) }

// Unlock releases sync.lock; later calls do nothing.
func (l *SyncLock) Unlock() {
	l.once.Do(func() {
		close(l.stop)
		_ = os.Remove(filepath.Join(l.dir, syncLockFile))
	})
}

// ReadSynced is state.json as it is now, for a question only (status, a dry
// run): no lock. Never save what it returns.
func ReadSynced(dir string) (*Synced, error) { return loadSynced(dir) }
