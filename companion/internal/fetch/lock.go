package fetch

import (
	"errors"
	"os"
	"path/filepath"
	"time"
)

// ErrLocked means another process holds the fetch lock.
var ErrLocked = errors.New("another fetch is running")

// staleLock is how old a lock file must be before its holder counts as gone.
const staleLock = 2 * time.Hour

// Lock takes the fetch lock in dir, so the launcher, the scheduled task and
// the importer never change fetched.json at the same time. A lock older than
// two hours is taken over: its holder is clearly gone. The returned function
// releases it.
func Lock(dir string) (func(), error) {
	path := filepath.Join(dir, "fetch.lock")
	for range 2 {
		f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
		if err == nil {
			f.Close()
			return func() { os.Remove(path) }, nil
		}
		if info, serr := os.Stat(path); serr == nil && time.Since(info.ModTime()) > staleLock {
			os.Remove(path)
			continue
		}
		break
	}
	return nil, ErrLocked
}
