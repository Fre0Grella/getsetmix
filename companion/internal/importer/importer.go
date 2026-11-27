// Package importer is one sync: find files that arrived in the watched
// folders, and add the ones Rekordbox doesn't have to its collection. A
// track the server changed, whose newer copy fetch put in place of the old
// one, has its existing row updated instead (docs/design/library.md, 4.6).
//
// The order is what makes it safe:
//
//  1. scan the folders, and compare the tracks the server removed with the
//     ones already listed in the "removed on server" playlist; stop here if
//     nothing is new or changed (the common case — no database is opened at
//     all);
//  2. refuse to write while Rekordbox is running;
//  3. read the collection to drop files it already has, and probe the rest;
//  4. back up master.db, write everything, check integrity, and put the
//     backup back if anything failed.
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

	"github.com/Fre0Grella/getsetmix/companion/internal/atomicfile"
	"github.com/Fre0Grella/getsetmix/companion/internal/audio"
	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/ledger"
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
	Changed  int               // files in the collection the server sent a newer copy of
	Updated  []string          // their rows, brought in line with the file
	NoRow    []string          // changed, but no longer in Rekordbox: not imported again
	Failed   map[string]string // path -> reason; retried next sync
	Deferred bool              // Rekordbox is open: nothing was written
	DryRun   bool
	// Tracks the server removed, listed in the "removed on server"
	// playlist, and restored ones taken out of it (removed.go).
	MarkedRemoved []string
	Unmarked      []string
}

// quickCheck is the integrity check after a write; tests replace it.
var quickCheck = (*library.DB).QuickCheck

// fetched is fetched.json held under fetch.lock, for a sync that updates
// rows: the tracks whose newer copy fetch put in place and Rekordbox does not
// have yet are in its work.
type fetched struct {
	state *ledger.Fetched
	lock  *ledger.FetchLock
	seen  map[string]library.Tags // path key -> the tags that file holds now
}

// work is what the sync does about the server's tracks (ledger.WorkFor),
// from the sync's one look at fetched.json. When a file in ready waits for
// its row to be updated, it takes fetch.lock and asks again on a fresh read,
// since a fetch may have finished meanwhile; held is then that read, under
// the lock. While a fetch runs the changed tracks wait for the next sync: the
// work then has none. Without a paired server there is no work.
func (im *Importer) work(ready []scan.File, state *ledger.Synced) (ledger.Work, *fetched, error) {
	if im.Config.Server == nil || im.Config.Server.Folder == "" {
		return ledger.WorkFor(nil, state, ""), nil, nil
	}
	folder := im.Config.Server.Folder
	snap, err := ledger.ReadFetched(im.Home)
	if err != nil {
		return ledger.Work{}, nil, err
	}
	w := ledger.WorkFor(snap, state, folder)
	if !slices.ContainsFunc(ready, func(f scan.File) bool { _, ok := w.Changed[f.Key]; return ok }) {
		return w, nil, nil
	}
	lock, err := ledger.LockFetch(im.Home)
	if errors.Is(err, ledger.ErrFetchRunning) {
		im.Log.Printf("a fetch is running: changed tracks are updated in Rekordbox on the next sync")
		w.Changed = nil
		return w, nil, nil
	}
	if err != nil {
		return ledger.Work{}, nil, err
	}
	fresh, err := lock.Load()
	if err != nil {
		lock.Unlock()
		return ledger.Work{}, nil, err
	}
	return ledger.WorkFor(fresh, state, folder),
		&fetched{state: fresh, lock: lock, seen: map[string]library.Tags{}}, nil
}

// Split sorts the ready files into what a sync acts on: pending ones were
// never handled; changed ones were, and fetch has since put a newer copy
// from the server in their place (w.Changed). `status` counts with it too.
func Split(ready []scan.File, state *ledger.Synced, w ledger.Work) (pending, changed []scan.File) {
	pending = state.Unhandled(ready)
	for _, f := range ready {
		_, waits := w.Changed[f.Key]
		if _, done := state.Seen[f.Key]; done && waits {
			changed = append(changed, f)
		}
	}
	return pending, changed
}

// ErrRekordboxRunning is returned by Sync when files wait but Rekordbox is open.
var ErrRekordboxRunning = errors.New("tracks wait while Rekordbox is running; they will be imported once it is closed")

// ErrSyncRunning is returned by Sync when another sync still ran after
// syncWait: this one did nothing, and the next one picks its files up.
var ErrSyncRunning = ledger.ErrSyncRunning

// syncWait is how long a sync waits for another one to end. Long enough for
// the launcher to import right after the scheduled sync; tests shorten it.
var syncWait = 30 * time.Second

// Sync performs one sync. With dryRun it reports what it would import and
// writes nothing at all (not even state).
//
// One sync runs at a time: a sync holds sync.lock throughout, and waits up
// to syncWait for another one to end; then it returns ErrSyncRunning. A dry
// run writes nothing and takes no lock.
func (im *Importer) Sync(dryRun bool) (Report, error) {
	rep := Report{Failed: map[string]string{}, DryRun: dryRun}
	var state *ledger.Synced
	var lock *ledger.SyncLock
	var err error
	if dryRun {
		state, err = ledger.ReadSynced(im.Home)
	} else if lock, err = ledger.LockSync(im.Home, syncWait); err == nil {
		defer lock.Unlock()
		state, err = lock.Load()
	} else if errors.Is(err, ErrSyncRunning) {
		im.Log.Printf("another sync is still running: this one is skipped")
	}
	if err != nil {
		return rep, err
	}
	now := im.Now()
	found, err := scan.Folders(im.Config.Folders, now)
	if err != nil {
		return rep, err
	}
	rep.Settling = len(found.Settling)
	// A state from before link protocol 2 holds when each file was handled,
	// not its size and time: they are taken from the file as it is now, and
	// nothing is acted on (docs/design/library.md, 4.6).
	if state.Widen(found.Ready) && !dryRun {
		if err := lock.Save(state); err != nil {
			return rep, err
		}
	}
	// A handled file is acted on when fetch put a newer copy from the server in
	// its place: only then are the fields that changed on the server known.
	// Changes in folders a sync client fills come with local mode
	// (docs/design/library.md, 4.7) and are left alone here.
	work, known, err := im.work(found.Ready, state)
	if err != nil {
		return rep, err
	}
	if known != nil {
		defer known.lock.Unlock()
	}
	pending, changed := Split(found.Ready, state, work)
	// The library names its results by the paths it was given, so they lead
	// back to the scanned files without building a key again.
	byPath := map[string]scan.File{}
	for _, f := range append(slices.Clone(pending), changed...) {
		byPath[f.Path] = f
	}
	rep.New = len(pending)
	rep.Changed = len(changed)
	marks := marksOf(work)
	if len(pending) == 0 && len(changed) == 0 && marks.empty() {
		return rep, nil
	}

	if running, err := im.IsRunning(); err != nil {
		return rep, err
	} else if running {
		rep.Deferred = true
		return rep, ErrRekordboxRunning
	}

	var tracks []library.Track
	var updates []library.Change
	if len(pending) > 0 || len(changed) > 0 {
		if tracks, updates, err = im.prepare(pending, changed, work, known, &rep); err != nil {
			return rep, err
		}
	}
	if dryRun {
		for _, t := range tracks {
			rep.Imported = append(rep.Imported, t.Path)
		}
		for _, u := range updates {
			rep.Updated = append(rep.Updated, u.Path)
		}
		rep.MarkedRemoved, rep.Unmarked = marks.add, marks.drop
		return rep, nil
	}
	if len(tracks) > 0 || len(updates) > 0 || !marks.empty() {
		if err := im.write(tracks, updates, marks, now, &rep); err != nil {
			return rep, err
		}
	}

	for _, p := range slices.Concat(rep.Imported, rep.Already, rep.Updated, rep.NoRow) {
		f, ok := byPath[p]
		if !ok { // the library answers with the paths it was given; never expected
			im.Log.Printf("warning: %s was not among the scanned files; it is looked at again next sync", p)
			continue
		}
		state.Handled(now, f)
	}
	state.Listed(now, work.Removed...)
	state.Unlisted(work.Restored...)
	var fetchedErr error
	if known != nil && len(known.seen) > 0 {
		// The tags of the files as they are now are the ones seen from here on.
		for _, p := range slices.Concat(rep.Imported, rep.Updated, rep.NoRow) {
			key := byPath[p].Key
			if tags, ok := known.seen[key]; ok {
				known.state.Applied(work.Changed[key], tags)
			}
		}
		fetchedErr = known.lock.Save(known.state)
	}
	return rep, errors.Join(fetchedErr, lock.Save(state))
}

// prepare drops files the collection already has and probes the rest, and
// works out what to write for each changed file: the fields that changed on
// the server since this computer last saw them.
func (im *Importer) prepare(pending, changed []scan.File, work ledger.Work, ft *fetched,
	rep *Report) ([]library.Track, []library.Change, error) {
	// Read-write mode although we only read: Rekordbox is known to be closed,
	// and only a writable connection checkpoints and removes the WAL file on
	// close instead of leaving an empty one in Rekordbox's folder.
	db, err := library.Open(im.Install.DB())
	if err != nil {
		return nil, nil, err
	}
	inCollection, err := db.KnownPaths()
	db.Close()
	if err != nil {
		return nil, nil, err
	}
	var tracks []library.Track
	for _, f := range pending {
		_, stale := work.Changed[f.Key]
		if inCollection[f.Key] {
			if stale { // not handled yet, but its row is older than the file
				changed = append(changed, f)
			} else {
				rep.Already = append(rep.Already, f.Path)
			}
			continue
		}
		t, err := audio.Probe(f.Path)
		if err != nil {
			rep.Failed[f.Path] = err.Error()
			im.Log.Printf("skip %s: %v", filepath.Base(f.Path), err)
			continue
		}
		if stale {
			ft.seen[f.Key] = audio.TagsOf(t)
		}
		tracks = append(tracks, t)
	}
	rep.Changed = len(changed)
	var updates []library.Change
	for _, f := range changed {
		t, err := audio.Probe(f.Path)
		if err != nil {
			rep.Failed[f.Path] = err.Error()
			im.Log.Printf("skip the changed %s: %v", filepath.Base(f.Path), err)
			continue
		}
		tags := audio.TagsOf(t)
		ft.seen[f.Key] = tags
		if !inCollection[f.Key] {
			// The DJ removed the track from Rekordbox: it stays removed.
			rep.NoRow = append(rep.NoRow, f.Path)
			continue
		}
		// Only the fields that changed on the server are written, so an edit
		// made in Rekordbox to another field is kept; where both changed the
		// same field, the server's value wins.
		was := work.Changed[f.Key].Was
		updates = append(updates, library.Change{Path: f.Path, Tags: tags,
			Fields: library.Changed(was, tags), FileSize: t.FileSize, FileID: t.FileID})
	}
	return tracks, updates, nil
}

// write imports tracks, updates the rows of changed files and updates the
// "removed on server" playlist, under a backup that is restored if anything
// is off.
func (im *Importer) write(tracks []library.Track, updates []library.Change, marks removals,
	now time.Time, rep *Report) error {
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
	var upd library.UpdateResult
	var importErr, updateErr, markErr error
	if len(tracks) > 0 {
		res, importErr = db.Import(tracks, im.Config.Playlist, now)
	}
	if importErr == nil && len(updates) > 0 {
		upd, updateErr = db.Update(updates, now)
	}
	var marked library.RemovedResult
	if importErr == nil && updateErr == nil && !marks.empty() {
		// After the import, so a track fetched and removed before Rekordbox
		// was closed has its row by now.
		marked, markErr = db.MarkRemoved(marks.add, marks.drop, now)
	}
	checkErr := quickCheck(db)
	closeErr := db.Close()
	if err := errors.Join(importErr, updateErr, markErr, checkErr, closeErr); err != nil {
		if restoreErr := restore(backup, im.Install.Dir); restoreErr != nil {
			return fmt.Errorf("%w; restoring the backup also failed: %v (copy %s back by hand)",
				err, restoreErr, backup)
		}
		return fmt.Errorf("%w (master.db was restored from the backup)", err)
	}
	rep.Imported = append(rep.Imported, res.Added...)
	rep.Already = append(rep.Already, res.Skipped...)
	rep.Updated = append(rep.Updated, upd.Updated...)
	rep.NoRow = append(rep.NoRow, upd.Missing...)
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
	return atomicfile.Write(dst, 0o644, func(w io.Writer) error {
		_, err := io.Copy(w, in)
		return err
	})
}
