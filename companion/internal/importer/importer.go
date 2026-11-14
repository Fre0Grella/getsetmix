// Package importer is one sync: find files that arrived in the watched
// folders, and add the ones Rekordbox doesn't have to its collection.
//
// The order is what makes it safe:
//
//  1. scan the folders, and compare the tracks the server removed with the
//     ones already listed in the "removed on server" playlist; stop here if
//     nothing is new (the common case — no database is opened at all);
//  2. refuse to write while Rekordbox is running;
//  3. read the collection to drop files it already has, and probe the rest;
//  4. back up master.db, write everything in one transaction, check integrity,
//     and put the backup back if the check fails.
package importer

import (
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"slices"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/audio"
	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/rekordbox"
	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
)

// Importer syncs the configured folders into one Rekordbox library.
type Importer struct {
	Install rekordbox.Install
	Config  config.Config
	Home    string // companion folder: state.json and the backup live here
	Log     *log.Logger
	Now     func() time.Time

	// IsRunning reports whether Rekordbox is open (overridable in tests).
	IsRunning func() (bool, error)
}

// Report says what a sync did.
type Report struct {
	New      int               // files not handled before
	Settling int               // files still being written; picked up later
	Imported []string          // added to the collection
	Already  []string          // were in the collection already
	Failed   map[string]string // path -> reason; retried next sync
	Deferred bool              // Rekordbox is open: nothing was written
	DryRun   bool
	// Tracks the server removed, listed in the "removed on server"
	// playlist, and restored ones taken out of it (removed.go).
	MarkedRemoved []string
	Unmarked      []string
}

// ErrRekordboxRunning is returned by Sync when files wait but Rekordbox is open.
var ErrRekordboxRunning = errors.New("Rekordbox is running; tracks will be imported once it is closed")

// Sync performs one sync. With dryRun it reports what it would import and
// writes nothing at all (not even state).
func (im *Importer) Sync(dryRun bool) (Report, error) {
	rep := Report{Failed: map[string]string{}, DryRun: dryRun}
	now := im.Now()
	state, err := config.LoadState(im.Home)
	if err != nil {
		return rep, err
	}
	found, err := scan.Folders(im.Config.Folders, now)
	if err != nil {
		return rep, err
	}
	rep.Settling = len(found.Settling)
	// A state from before link protocol 2 holds when each file was handled,
	// not its size and time: they are taken from the file as it is now, and
	// nothing is acted on (docs/design/library.md, 4.6).
	if state.Widen(found.Ready) && !dryRun {
		if err := state.Save(im.Home); err != nil {
			return rep, err
		}
	}
	var pending []scan.File
	byKey := map[string]scan.File{}
	for _, f := range found.Ready {
		if _, done := state.Seen[f.Key]; !done {
			pending = append(pending, f)
			byKey[f.Key] = f
		}
	}
	rep.New = len(pending)
	marks, err := im.removals(state)
	if err != nil {
		return rep, err
	}
	if len(pending) == 0 && marks.empty() {
		return rep, nil
	}

	if running, err := im.IsRunning(); err != nil {
		return rep, err
	} else if running {
		rep.Deferred = true
		return rep, ErrRekordboxRunning
	}

	var tracks []library.Track
	if len(pending) > 0 {
		if tracks, err = im.prepare(pending, &rep); err != nil {
			return rep, err
		}
	}
	if dryRun {
		for _, t := range tracks {
			rep.Imported = append(rep.Imported, t.Path)
		}
		rep.MarkedRemoved, rep.Unmarked = marks.add, marks.drop
		return rep, nil
	}
	if len(tracks) > 0 || !marks.empty() {
		if err := im.write(tracks, marks, now, &rep); err != nil {
			return rep, err
		}
	}

	for _, p := range slices.Concat(rep.Imported, rep.Already) {
		key := library.PathKey(p)
		f, ok := byKey[key]
		if !ok {
			f = scan.File{Path: p, Key: key}
		}
		state.Mark(now, f)
	}
	marks.record(state, now)
	return rep, state.Save(im.Home)
}

// prepare drops files the collection already has and probes the rest.
func (im *Importer) prepare(pending []scan.File, rep *Report) ([]library.Track, error) {
	// Read-write mode although we only read: Rekordbox is known to be closed,
	// and only a writable connection checkpoints and removes the WAL file on
	// close instead of leaving an empty one in Rekordbox's folder.
	db, err := library.Open(im.Install.DB())
	if err != nil {
		return nil, err
	}
	known, err := db.KnownPaths()
	db.Close()
	if err != nil {
		return nil, err
	}
	var tracks []library.Track
	for _, f := range pending {
		if known[f.Key] {
			rep.Already = append(rep.Already, f.Path)
			continue
		}
		t, err := audio.Probe(f.Path)
		if err != nil {
			rep.Failed[f.Path] = err.Error()
			im.Log.Printf("skip %s: %v", filepath.Base(f.Path), err)
			continue
		}
		tracks = append(tracks, t)
	}
	return tracks, nil
}

// write imports tracks and updates the "removed on server" playlist under a
// backup that is restored if anything is off.
func (im *Importer) write(tracks []library.Track, marks removals, now time.Time, rep *Report) error {
	backup := filepath.Join(im.Home, "backup")
	if err := snapshot(im.Install.Dir, backup); err != nil {
		return fmt.Errorf("backing up master.db (nothing was changed): %w", err)
	}
	// Re-check: Rekordbox may have been opened while we were probing.
	if running, err := im.IsRunning(); err != nil {
		return err
	} else if running {
		rep.Deferred = true
		return ErrRekordboxRunning
	}

	db, err := library.Open(im.Install.DB())
	if err != nil {
		return err
	}
	var res library.Result
	var importErr, markErr error
	if len(tracks) > 0 {
		res, importErr = db.Import(tracks, im.Config.Playlist, now)
	}
	var marked library.RemovedResult
	if importErr == nil && !marks.empty() {
		// After the import, so a track fetched and removed before Rekordbox
		// was closed has its row by now.
		marked, markErr = db.MarkRemoved(marks.add, marks.drop, now)
	}
	checkErr := db.QuickCheck()
	closeErr := db.Close()
	if err := errors.Join(importErr, markErr, checkErr, closeErr); err != nil {
		if restoreErr := restore(backup, im.Install.Dir); restoreErr != nil {
			return fmt.Errorf("%w; restoring the backup also failed: %v (copy %s back by hand)",
				err, restoreErr, backup)
		}
		return fmt.Errorf("%w (master.db was restored from the backup)", err)
	}
	rep.Imported = append(rep.Imported, res.Added...)
	rep.Already = append(rep.Already, res.Skipped...)
	rep.MarkedRemoved = append(rep.MarkedRemoved, marked.Added...)
	rep.Unmarked = append(rep.Unmarked, marked.Dropped...)
	for _, pl := range []library.Playlist{res.Playlist, marked.Playlist} {
		if pl.ID == "" {
			continue
		}
		if err := library.SyncPlaylistXML(im.Install.PlaylistXML(), pl); err != nil {
			// The rows are in; Rekordbox rebuilds this mirror if it must.
			im.Log.Printf("warning: masterPlaylists6.xml not updated: %v", err)
		}
	}
	return nil
}

// Files copied before a write: the database, its WAL if Rekordbox left one,
// and the playlist mirror.
var snapshotFiles = []string{"master.db", "master.db-wal", "masterPlaylists6.xml"}

func snapshot(srcDir, dstDir string) error {
	if err := os.MkdirAll(dstDir, 0o755); err != nil {
		return err
	}
	for _, name := range snapshotFiles {
		dst := filepath.Join(dstDir, name)
		if err := copyFile(filepath.Join(srcDir, name), dst); errors.Is(err, os.ErrNotExist) {
			_ = os.Remove(dst) // keep the backup a consistent set
		} else if err != nil {
			return err
		}
	}
	return nil
}

func restore(backupDir, dstDir string) error {
	var errs []error
	for _, name := range snapshotFiles {
		src := filepath.Join(backupDir, name)
		if _, err := os.Stat(src); err != nil {
			_ = os.Remove(filepath.Join(dstDir, name))
			continue
		}
		errs = append(errs, copyFile(src, filepath.Join(dstDir, name)))
	}
	_ = os.Remove(filepath.Join(dstDir, "master.db-shm"))
	return errors.Join(errs...)
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	tmp := dst + ".tmp"
	out, err := os.Create(tmp)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, dst)
}
