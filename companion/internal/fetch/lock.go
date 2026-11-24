package fetch

import (
	"context"
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

// RunLocked is one whole fetch the way every caller must do it: take the
// lock, read fetched.json, download from s, and save the state again even
// when the run stopped early (what was fetched is recorded). It returns the
// report and the state as saved, for the caller's own reporting.
func RunLocked(ctx context.Context, dir string, s Server, now func() time.Time) (Report, *State, error) {
	unlock, err := Lock(dir)
	if err != nil {
		return Report{}, nil, err
	}
	defer unlock()
	state, err := LoadState(dir)
	if err != nil {
		return Report{}, nil, err
	}
	rep, err := (&Client{Server: s}).Run(ctx, state, now)
	if serr := state.Save(dir); err == nil {
		err = serr
	}
	return rep, state, err
}
