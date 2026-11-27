package fetch

import (
	"context"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/ledger"
)

// RunLocked is one whole fetch the way every caller must do it: take
// fetch.lock, read fetched.json, download from s, and save the state again
// even when the run stopped early (what was fetched is recorded). The
// launcher, the scheduled task and Setup's dry run all run it. It returns the
// report and the state as saved, for the caller's own reporting; while
// another fetch runs it returns ledger.ErrFetchRunning.
func RunLocked(ctx context.Context, dir string, s config.Server, now func() time.Time) (Report, *ledger.Fetched, error) {
	lock, err := ledger.LockFetch(dir)
	if err != nil {
		return Report{}, nil, err
	}
	defer lock.Unlock()
	state, err := lock.Load()
	if err != nil {
		return Report{}, nil, err
	}
	rep, err := (&Client{Server: s}).Run(ctx, state, now)
	if serr := lock.Save(state); err == nil {
		err = serr
	}
	return rep, state, err
}

// Seed decides what the first fetch downloads: everything the server has,
// or (all false) only what arrives from now on. Setup calls it on pairing.
//
// Only on first pairing: a computer that already fetched keeps its state,
// whatever the choice, or Setup run again would forget what it holds and
// what the server removed, and fetch again over local files.
func Seed(ctx context.Context, dir string, s config.Server, all bool, now time.Time) error {
	lock, err := ledger.LockFetch(dir)
	if err != nil {
		return err
	}
	defer lock.Unlock()
	if held, err := lock.Load(); err != nil {
		return err
	} else if !held.Empty() {
		return nil
	}
	state := ledger.NewFetched()
	if !all {
		ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
		defer cancel()
		l, err := (&Client{Server: s}).List(ctx)
		if err != nil {
			return err
		}
		state.RecordAll(l, now)
	}
	return lock.Save(state)
}
