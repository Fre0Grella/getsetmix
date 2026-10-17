package importer

import (
	"bytes"
	"errors"
	"io"
	"log"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/library/librarytest"
	"github.com/Fre0Grella/getsetmix/companion/internal/rekordbox"
)

// mp3 is a tiny but valid MPEG-1 Layer III stream (20 frames, 320 kbps).
func mp3() []byte {
	frame := make([]byte, 1044)
	copy(frame, []byte{0xff, 0xfb, 0xe0, 0x00})
	return bytes.Repeat(frame, 20)
}

type env struct {
	im      *Importer
	music   string
	rbDir   string
	running bool
}

func newEnv(t *testing.T) *env {
	t.Helper()
	e := &env{music: t.TempDir(), rbDir: t.TempDir()}
	existing := filepath.Join(e.music, "already.mp3")
	librarytest.New(t, e.rbDir, library.FolderPath(existing))
	e.add(t, "already.mp3")
	e.im = &Importer{
		Install:   rekordbox.Install{Dir: e.rbDir},
		Config:    config.Config{Folders: []string{e.music}, Playlist: "GetSetMix"},
		Home:      t.TempDir(),
		Log:       log.New(io.Discard, "", 0),
		Now:       time.Now,
		IsRunning: func() (bool, error) { return e.running, nil },
	}
	return e
}

// add drops a settled audio file into the watched folder.
func (e *env) add(t *testing.T, name string) string {
	t.Helper()
	path := filepath.Join(e.music, name)
	if err := os.WriteFile(path, mp3(), 0o644); err != nil {
		t.Fatal(err)
	}
	old := time.Now().Add(-time.Minute)
	os.Chtimes(path, old, old)
	return path
}

func (e *env) count(t *testing.T, q string) int {
	t.Helper()
	db := librarytest.Open(t, filepath.Join(e.rbDir, "master.db"))
	defer db.Close()
	var n int
	if err := db.QueryRow(q).Scan(&n); err != nil {
		t.Fatal(err)
	}
	return n
}

func TestSyncImportsNewTracksOnce(t *testing.T) {
	e := newEnv(t)
	e.add(t, "new one.mp3")
	e.add(t, "new two.mp3")

	rep, err := e.im.Sync(false)
	if err != nil {
		t.Fatal(err)
	}
	if len(rep.Imported) != 2 || len(rep.Already) != 1 {
		t.Fatalf("report: %+v", rep)
	}
	if n := e.count(t, "SELECT count(*) FROM djmdContent"); n != 3 {
		t.Errorf("collection has %d tracks, want 3", n)
	}
	if n := e.count(t, `SELECT count(*) FROM djmdSongPlaylist s JOIN djmdPlaylist p
		ON p.ID = s.PlaylistID WHERE p.Name = 'GetSetMix'`); n != 2 {
		t.Errorf("playlist has %d tracks, want 2", n)
	}
	if _, err := os.Stat(filepath.Join(e.im.Home, "backup", "master.db")); err != nil {
		t.Errorf("no backup taken: %v", err)
	}
	xml, _ := os.ReadFile(filepath.Join(e.rbDir, "masterPlaylists6.xml"))
	if bytes.Count(xml, []byte("<NODE ")) != 2 {
		t.Errorf("playlist not mirrored into masterPlaylists6.xml:\n%s", xml)
	}

	// Nothing new: the database is not even opened, let alone written.
	before, _ := os.Stat(filepath.Join(e.rbDir, "master.db"))
	rep, err = e.im.Sync(false)
	if err != nil || rep.New != 0 {
		t.Fatalf("second sync: %+v, %v", rep, err)
	}
	after, _ := os.Stat(filepath.Join(e.rbDir, "master.db"))
	if !after.ModTime().Equal(before.ModTime()) {
		t.Error("master.db was touched although nothing was new")
	}
}

func TestDeletedFromRekordboxStaysDeleted(t *testing.T) {
	e := newEnv(t)
	e.add(t, "keeper.mp3")
	if _, err := e.im.Sync(false); err != nil {
		t.Fatal(err)
	}
	db := librarytest.Open(t, filepath.Join(e.rbDir, "master.db"))
	db.Exec("DELETE FROM djmdContent WHERE FileNameL = 'keeper.mp3'")
	db.Close()

	rep, err := e.im.Sync(false)
	if err != nil || rep.New != 0 || len(rep.Imported) != 0 {
		t.Fatalf("a track removed in Rekordbox was re-imported: %+v, %v", rep, err)
	}
}

func TestSyncDefersWhileRekordboxRuns(t *testing.T) {
	e := newEnv(t)
	e.add(t, "later.mp3")
	e.running = true
	rep, err := e.im.Sync(false)
	if !errors.Is(err, ErrRekordboxRunning) || !rep.Deferred {
		t.Fatalf("want deferral, got %+v, %v", rep, err)
	}
	if n := e.count(t, "SELECT count(*) FROM djmdContent"); n != 1 {
		t.Fatal("wrote to master.db while Rekordbox was running")
	}
	e.running = false
	if rep, err := e.im.Sync(false); err != nil || len(rep.Imported) != 1 {
		t.Fatalf("after Rekordbox closed: %+v, %v", rep, err)
	}
}

func TestDryRunChangesNothing(t *testing.T) {
	e := newEnv(t)
	e.add(t, "maybe.mp3")
	rep, err := e.im.Sync(true)
	if err != nil || len(rep.Imported) != 1 {
		t.Fatalf("%+v, %v", rep, err)
	}
	if n := e.count(t, "SELECT count(*) FROM djmdContent"); n != 1 {
		t.Error("dry run wrote to master.db")
	}
	if rep, _ := e.im.Sync(true); len(rep.Imported) != 1 {
		t.Error("dry run recorded state")
	}
}

func TestUnreadableFilesAreRetriedNotImported(t *testing.T) {
	e := newEnv(t)
	bad := filepath.Join(e.music, "broken.mp3")
	os.WriteFile(bad, bytes.Repeat([]byte("junk"), 500), 0o644)
	old := time.Now().Add(-time.Minute)
	os.Chtimes(bad, old, old)

	rep, err := e.im.Sync(false)
	if err != nil || len(rep.Failed) != 1 || len(rep.Imported) != 0 {
		t.Fatalf("%+v, %v", rep, err)
	}
	if rep, _ := e.im.Sync(false); rep.New != 1 {
		t.Error("a failed file should be retried on the next sync")
	}
}

func TestFailedIntegrityRestoresBackup(t *testing.T) {
	e := newEnv(t)
	e.add(t, "x.mp3")
	if err := snapshot(e.rbDir, filepath.Join(e.im.Home, "backup")); err != nil {
		t.Fatal(err)
	}
	// Simulate a write gone wrong after the snapshot was taken.
	db := librarytest.Open(t, filepath.Join(e.rbDir, "master.db"))
	db.Exec("INSERT INTO djmdGenre (ID, Name, created_at, updated_at) VALUES ('1', 'junk', 'x', 'x')")
	db.Close()
	if err := restore(filepath.Join(e.im.Home, "backup"), e.rbDir); err != nil {
		t.Fatal(err)
	}
	if n := e.count(t, "SELECT count(*) FROM djmdGenre"); n != 0 {
		t.Error("restore did not bring the database back")
	}
}
