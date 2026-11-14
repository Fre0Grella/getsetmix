package importer

import (
	"bytes"
	"database/sql"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/fetch"
	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/library/librarytest"
)

// pairedEnv is newEnv with a paired server that delivers into the watched
// folder, and one fetched track already imported, with a hot cue and a place
// in a playlist of the DJ's own.
func pairedEnv(t *testing.T) (*env, string) {
	t.Helper()
	e := newEnv(t)
	e.im.Config.Server = &fetch.Server{URL: "http://server", Token: "t", Folder: e.music}
	path := e.add(t, "House - Gone.mp3")
	if rep, err := e.im.Sync(false); err != nil || len(rep.Imported) != 1 {
		t.Fatalf("%+v, %v", rep, err)
	}
	e.exec(t, `INSERT INTO djmdCue (ID, ContentID, InMsec, Kind, created_at, updated_at)
		SELECT 'cue1', ID, 32000, 1, 'x', 'x' FROM djmdContent WHERE FileNameL = 'House - Gone.mp3'`)
	e.exec(t, `INSERT INTO djmdSongPlaylist (ID, PlaylistID, ContentID, TrackNo, created_at, updated_at)
		SELECT 'mine1', '200000', ID, 1, 'x', 'x' FROM djmdContent WHERE FileNameL = 'House - Gone.mp3'`)
	return e, path
}

func (e *env) exec(t *testing.T, q string) {
	t.Helper()
	raw := openRaw(t, e)
	defer raw.Close()
	if _, err := raw.Exec(q); err != nil {
		t.Fatal(err)
	}
}

// serverRemoves records what fetch records when the server removes (or, with
// gone false, restores) the track at serverPath.
func (e *env) serverRemoves(t *testing.T, serverPath string, gone bool) {
	t.Helper()
	state, err := fetch.LoadState(e.im.Home)
	if err != nil {
		t.Fatal(err)
	}
	state.Version = 2
	if gone {
		state.Removed["a1_gone"] = fetch.Tombstone{Path: serverPath, At: time.Now(), Reason: "deleted"}
	} else {
		delete(state.Removed, "a1_gone")
	}
	if err := state.Save(e.im.Home); err != nil {
		t.Fatal(err)
	}
}

func (e *env) inRemoved(t *testing.T) int {
	return e.count(t, `SELECT count(*) FROM djmdSongPlaylist s JOIN djmdPlaylist p ON p.ID = s.PlaylistID
		WHERE p.Name = '`+library.RemovedPlaylist+`'`)
}

func TestARemovedTrackLandsInThePlaylistOnce(t *testing.T) {
	e, path := pairedEnv(t)
	e.serverRemoves(t, "House - Gone.mp3", true)

	rep, err := e.im.Sync(false)
	if err != nil || !reflect.DeepEqual(rep.MarkedRemoved, []string{path}) || rep.New != 0 {
		t.Fatalf("%+v, %v", rep, err)
	}
	if n := e.inRemoved(t); n != 1 {
		t.Fatalf("removed playlist has %d tracks, want 1", n)
	}
	// Nothing is removed from the collection: the row, its cue, its place
	// in the DJ's playlist and the local file all stay.
	for q, want := range map[string]int{
		"SELECT count(*) FROM djmdContent WHERE FileNameL = 'House - Gone.mp3'": 1,
		"SELECT count(*) FROM djmdCue WHERE ID = 'cue1'":                        1,
		"SELECT count(*) FROM djmdSongPlaylist WHERE ID = 'mine1'":              1,
		"SELECT count(*) FROM djmdContent":                                      2,
	} {
		if n := e.count(t, q); n != want {
			t.Errorf("%s: %d, want %d", q, n, want)
		}
	}
	if _, err := os.Stat(path); err != nil {
		t.Errorf("the local file was touched: %v", err)
	}
	// Mirrored in masterPlaylists6.xml, next to the import playlist.
	xml, _ := os.ReadFile(filepath.Join(e.rbDir, "masterPlaylists6.xml"))
	if bytes.Count(xml, []byte("<NODE ")) != 3 || !strings.Contains(string(xml), removedNodeID(t, e)) {
		t.Errorf("removed playlist not mirrored:\n%s", xml)
	}

	// The next syncs: listed already, so master.db is not even opened.
	dbPath := filepath.Join(e.rbDir, "master.db")
	before, _ := os.Stat(dbPath)
	for range 2 {
		rep, err := e.im.Sync(false)
		if err != nil || len(rep.MarkedRemoved) != 0 {
			t.Fatalf("%+v, %v", rep, err)
		}
	}
	if after, _ := os.Stat(dbPath); !after.ModTime().Equal(before.ModTime()) {
		t.Error("master.db was touched with nothing to do")
	}
	if n := e.inRemoved(t); n != 1 {
		t.Fatalf("listed %d times", n)
	}
}

func TestARestoreTakesTheTrackOutOfThePlaylist(t *testing.T) {
	e, path := pairedEnv(t)
	e.serverRemoves(t, "House - Gone.mp3", true)
	if _, err := e.im.Sync(false); err != nil {
		t.Fatal(err)
	}
	e.serverRemoves(t, "House - Gone.mp3", false)
	rep, err := e.im.Sync(false)
	if err != nil || !reflect.DeepEqual(rep.Unmarked, []string{path}) {
		t.Fatalf("%+v, %v", rep, err)
	}
	if n := e.inRemoved(t); n != 0 {
		t.Fatalf("still listed: %d", n)
	}
	if n := e.count(t, "SELECT count(*) FROM djmdSongPlaylist WHERE ID = 'mine1'"); n != 1 {
		t.Error("the DJ's own playlist lost the track")
	}
	state, _ := config.LoadState(e.im.Home)
	if len(state.Removed) != 0 {
		t.Errorf("state %+v", state.Removed)
	}
	// Removed again later: listed again, once.
	e.serverRemoves(t, "House - Gone.mp3", true)
	if rep, err := e.im.Sync(false); err != nil || len(rep.MarkedRemoved) != 1 || e.inRemoved(t) != 1 {
		t.Fatalf("%+v, %v", rep, err)
	}
}

func TestNothingIsMarkedWhileRekordboxRuns(t *testing.T) {
	e, path := pairedEnv(t)
	e.serverRemoves(t, "House - Gone.mp3", true)
	dbPath := filepath.Join(e.rbDir, "master.db")
	before, _ := os.ReadFile(dbPath)
	xmlBefore, _ := os.ReadFile(filepath.Join(e.rbDir, "masterPlaylists6.xml"))

	e.running = true
	rep, err := e.im.Sync(false)
	if !errors.Is(err, ErrRekordboxRunning) || !rep.Deferred {
		t.Fatalf("want deferral, got %+v, %v", rep, err)
	}
	after, _ := os.ReadFile(dbPath)
	xmlAfter, _ := os.ReadFile(filepath.Join(e.rbDir, "masterPlaylists6.xml"))
	if !bytes.Equal(before, after) || !bytes.Equal(xmlBefore, xmlAfter) {
		t.Fatal("wrote while Rekordbox was running")
	}
	if state, _ := config.LoadState(e.im.Home); len(state.Removed) != 0 {
		t.Fatal("recorded as done while nothing was written")
	}

	e.running = false
	if rep, err := e.im.Sync(false); err != nil || !reflect.DeepEqual(rep.MarkedRemoved, []string{path}) {
		t.Fatalf("after Rekordbox closed: %+v, %v", rep, err)
	}
}

func TestADryRunShowsTheRemovedTracksAndWritesNothing(t *testing.T) {
	e, path := pairedEnv(t)
	e.serverRemoves(t, "House - Gone.mp3", true)
	rep, err := e.im.Sync(true)
	if err != nil || !reflect.DeepEqual(rep.MarkedRemoved, []string{path}) {
		t.Fatalf("%+v, %v", rep, err)
	}
	if n := e.inRemoved(t); n != 0 {
		t.Fatal("a dry run wrote the playlist")
	}
}

func TestATrackTheDJRemovedFromRekordboxIsNotLookedForAgain(t *testing.T) {
	e, _ := pairedEnv(t)
	e.exec(t, "DELETE FROM djmdContent WHERE FileNameL = 'House - Gone.mp3'")
	e.serverRemoves(t, "House - Gone.mp3", true)
	if rep, err := e.im.Sync(false); err != nil || len(rep.MarkedRemoved) != 0 {
		t.Fatalf("%+v, %v", rep, err)
	}
	dbPath := filepath.Join(e.rbDir, "master.db")
	before, _ := os.Stat(dbPath)
	if _, err := e.im.Sync(false); err != nil {
		t.Fatal(err)
	}
	if after, _ := os.Stat(dbPath); !after.ModTime().Equal(before.ModTime()) {
		t.Error("master.db opened again for a track it does not have")
	}
}

func TestWithoutAServerNothingIsMarked(t *testing.T) {
	e, _ := pairedEnv(t)
	e.serverRemoves(t, "House - Gone.mp3", true)
	e.im.Config.Server = nil
	if rep, err := e.im.Sync(false); err != nil || len(rep.MarkedRemoved) != 0 {
		t.Fatalf("%+v, %v", rep, err)
	}
}

func openRaw(t *testing.T, e *env) *sql.DB {
	t.Helper()
	return librarytest.Open(t, filepath.Join(e.rbDir, "master.db"))
}

func removedNodeID(t *testing.T, e *env) string {
	t.Helper()
	raw := openRaw(t, e)
	defer raw.Close()
	var id string
	if err := raw.QueryRow("SELECT ID FROM djmdPlaylist WHERE Name = ?", library.RemovedPlaylist).Scan(&id); err != nil {
		t.Fatal(err)
	}
	n, _ := strconv.ParseUint(id, 10, 64)
	return `Id="` + strings.ToUpper(strconv.FormatUint(n, 16)) + `"`
}
