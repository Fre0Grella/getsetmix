// Package watch keeps the companion resident and imports tracks as they
// arrive. It never polls: it sleeps on filesystem notifications
// (ReadDirectoryChangesW / FSEvents-kqueue) and, while Rekordbox is open, on
// the Rekordbox process handle — so between events it costs no CPU at all.
package watch

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"runtime/debug"
	"sync/atomic"
	"time"

	"github.com/fsnotify/fsnotify"

	"github.com/Fre0Grella/getsetmix/companion/internal/audio"
	"github.com/Fre0Grella/getsetmix/companion/internal/importer"
	"github.com/Fre0Grella/getsetmix/companion/internal/rekordbox"
	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
)

// Debounce coalesces a burst of events (a batch of downloads arriving, or
// the many writes of one large file) into a single sync.
const Debounce = 5 * time.Second

// Run syncs once, then again whenever the folders change, until ctx ends.
func Run(ctx context.Context, im *importer.Importer) error {
	w, err := fsnotify.NewWatcher()
	if err != nil {
		return err
	}
	defer w.Close()
	for _, root := range im.Config.Folders {
		if err := addTree(w, root); err != nil {
			return err
		}
	}

	trigger := make(chan struct{}, 1)
	poke := func() {
		select {
		case trigger <- struct{}{}:
		default: // a sync is already queued
		}
	}
	debounce := time.AfterFunc(time.Hour, poke)
	debounce.Stop()
	var waiting atomic.Bool // one goroutine at most waits for Rekordbox to close

	poke()
	for {
		select {
		case <-ctx.Done():
			return nil
		case err := <-w.Errors:
			im.Log.Printf("watch: %v", err)
		case ev := <-w.Events:
			if ev.Has(fsnotify.Create) {
				if info, err := os.Stat(ev.Name); err == nil && info.IsDir() {
					_ = addTree(w, ev.Name)
					debounce.Reset(Debounce)
					continue
				}
			}
			name := filepath.Base(ev.Name)
			if audio.Supported(name) && !scan.Ignored(name) {
				debounce.Reset(Debounce)
			}
		case <-trigger:
			rep, err := im.Sync(false)
			switch {
			case errors.Is(err, importer.ErrRekordboxRunning):
				if waiting.CompareAndSwap(false, true) {
					im.Log.Printf("%d new track(s) wait for Rekordbox to close", rep.New)
					go func() {
						defer waiting.Store(false)
						if rekordbox.WaitClosed(ctx) == nil {
							poke()
						}
					}()
				}
			case err != nil:
				im.Log.Printf("sync failed: %v", err)
			case len(rep.Imported) > 0:
				im.Log.Printf("imported %d track(s) into %q", len(rep.Imported), im.Config.Playlist)
			}
			// A sync briefly needs SQLCipher's page cache; hand it back so the
			// idle watcher stays a few MB instead of keeping its high-water mark.
			debug.FreeOSMemory()
			if rep.Settling > 0 {
				time.AfterFunc(scan.SettleTime+time.Second, poke)
			}
		}
	}
}

// addTree watches root and every folder below it (fsnotify is not recursive).
func addTree(w *fsnotify.Watcher, root string) error {
	return filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			if path == root {
				return err
			}
			return nil
		}
		if !d.IsDir() {
			return nil
		}
		if path != root && scan.Ignored(d.Name()) {
			return filepath.SkipDir
		}
		return w.Add(path)
	})
}
