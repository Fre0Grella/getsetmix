package importer

import (
	"database/sql"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"sort"
	"strconv"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/audio"
	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/ledger"
	"github.com/Fre0Grella/getsetmix/companion/internal/ledger/ledgertest"
	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/library/librarytest"
	"github.com/Fre0Grella/getsetmix/companion/internal/track"
	"github.com/Fre0Grella/getsetmix/companion/internal/track/tracktest"
)

var (
	onServerBefore = tracktest.Tags{Title: "Night Drive", Artist: "Some Artist", Album: "Nights",
		Genre: "House", Comment: "Source: https://example.test | via GetSetMix"}
	onServerAfter = tracktest.Tags{Title: "Night Drive", Artist: "Some Artist", Album: "Nights",
		Genre: "Tech House", Year: "2019", Comment: "warm-up"}
)

// fetchedTrack sets up a paired computer that fetched "Night Drive.mp3" and
// imported it, with cues, a rating, a play count, an analysis path and its
// place in a playlist that the DJ added in Rekordbox.
type fetchedTrack struct {
	*env
	path, id, contentID string
}

func newFetchedTrack(t *testing.T) *fetchedTrack {
	t.Helper()
	e := newEnv(t)
	e.im.Config.Server = &config.Server{URL: "http://server.test", Token: "tok", Folder: e.music}
	ft := &fetchedTrack{env: e, path: filepath.Join(e.music, "Night Drive.mp3")}
	ft.place(t, onServerBefore, time.Now().Add(-time.Hour))
	var err error
	if ft.id, err = audio.ID(ft.path); err != nil {
		t.Fatal(err)
	}
	tags, err := audio.ReadTags(ft.path)
	if err != nil {
		t.Fatal(err)
	}
	st := ledger.NewFetched()
	st.Version = 2
	st.Tracks[ft.id] = ledger.Track{Path: "Night Drive.mp3", Rev: 5, At: time.Now(), Tags: &tags}
	ledgertest.Save(t, e.im.Home, st)
	if rep, err := e.im.Sync(false); err != nil || len(rep.Imported) != 1 {
		t.Fatalf("import: %+v, %v", rep, err)
	}
	db := librarytest.Open(t, filepath.Join(e.rbDir, "master.db"))
	defer db.Close()
	if err := db.QueryRow("SELECT ID FROM djmdContent WHERE FileNameL = 'Night Drive.mp3'").
		Scan(&ft.contentID); err != nil {
		t.Fatal(err)
	}
	for _, q := range []string{
		`UPDATE djmdContent SET Rating = 4, DJPlayCount = 12, BPM = 12400,
			AnalysisDataPath = '/PIONEER/USBANLZ/abc/ANLZ0000.DAT', ColorID = '3' WHERE ID = ?`,
		`INSERT INTO djmdCue (ID, ContentID, InMsec, Kind, Comment, created_at, updated_at)
			VALUES ('c1', ?, 1500, 1, 'drop', 'x', 'x')`,
		`INSERT INTO djmdCue (ID, ContentID, InMsec, Kind, Comment, created_at, updated_at)
			VALUES ('c2', ?, 64000, 0, '', 'x', 'x')`,
		`INSERT INTO djmdSongPlaylist (ID, PlaylistID, ContentID, TrackNo, created_at, updated_at)
			VALUES ('sp1', '200000', ?, 1, 'x', 'x')`,
	} {
		if _, err := db.Exec(q, ft.contentID); err != nil {
			t.Fatal(err)
		}
	}
	return ft
}

// place writes the track with tags, replacing the file by a rename as fetch
// does, so it gets a new filesystem id.
func (ft *fetchedTrack) place(t *testing.T, tags tracktest.Tags, mtime time.Time) {
	t.Helper()
	tmp := ft.path + ".part"
	if err := os.WriteFile(tmp, tracktest.MP3(7, tags), 0o644); err != nil {
		t.Fatal(err)
	}
	os.Chtimes(tmp, mtime, mtime)
	if err := os.Rename(tmp, ft.path); err != nil {
		t.Fatal(err)
	}
}

// refresh is what fetch does when the server changed the track.
func (ft *fetchedTrack) refresh(t *testing.T) {
	t.Helper()
	ft.place(t, onServerAfter, time.Now().Add(-30*time.Minute))
	st, err := ledger.ReadFetched(ft.im.Home)
	if err != nil {
		t.Fatal(err)
	}
	held := st.Tracks[ft.id]
	held.Rev, held.Pending = 9, true
	st.Tracks[ft.id] = held
	ledgertest.Save(t, ft.im.Home, st)
}

func (ft *fetchedTrack) db(t *testing.T) *sql.DB {
	t.Helper()
	return librarytest.Open(t, filepath.Join(ft.rbDir, "master.db"))
}

// rows reads every row of a query as column -> value text.
func rows(t *testing.T, db *sql.DB, q string, args ...any) []map[string]string {
	t.Helper()
	r, err := db.Query(q, args...)
	if err != nil {
		t.Fatal(err)
	}
	defer r.Close()
	cols, _ := r.Columns()
	var out []map[string]string
	for r.Next() {
		vals := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range vals {
			ptrs[i] = &vals[i]
		}
		if err := r.Scan(ptrs...); err != nil {
			t.Fatal(err)
		}
		m := map[string]string{}
		for i, c := range cols {
			m[c] = fmt.Sprint(vals[i])
		}
		out = append(out, m)
	}
	return out
}

func (ft *fetchedTrack) row(t *testing.T) map[string]string {
	t.Helper()
	db := librarytest.Open(t, filepath.Join(ft.rbDir, "master.db"))
	defer db.Close()
	// The driver cannot parse Rekordbox's timestamps: compare them as text.
	return rows(t, db, `SELECT *, CAST(created_at AS TEXT) AS created_text,
		CAST(updated_at AS TEXT) AS updated_text FROM djmdContent WHERE ID = ?`, ft.contentID)[0]
}

func named(t *testing.T, db *sql.DB, table, id string) string {
	t.Helper()
	var name string
	if err := db.QueryRow("SELECT Name FROM "+table+" WHERE ID = ?", id).Scan(&name); err != nil {
		t.Fatalf("%s %s: %v", table, id, err)
	}
	return name
}

func usn(t *testing.T, db *sql.DB) int64 {
	t.Helper()
	var n int64
	if err := db.QueryRow(
		"SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'").Scan(&n); err != nil {
		t.Fatal(err)
	}
	return n
}

// The heart of slice 3 on the computer (docs/design/library.md, 4.6): a
// changed track updates exactly the columns in the design, only for the
// fields that changed on the server, and leaves everything else alone.
func TestAChangedTrackUpdatesExactlyItsColumns(t *testing.T) {
	ft := newFetchedTrack(t)
	db := ft.db(t)
	// The DJ changed the artist and the genre in Rekordbox meanwhile.
	if _, err := db.Exec(`INSERT INTO djmdArtist (ID, Name, created_at, updated_at)
		VALUES ('9001', 'DJ Edit', 'x', 'x')`); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO djmdGenre (ID, Name, created_at, updated_at)
		VALUES ('9002', 'Rekordbox Genre', 'x', 'x')`); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec("UPDATE djmdContent SET ArtistID = '9001', GenreID = '9002' WHERE ID = ?",
		ft.contentID); err != nil {
		t.Fatal(err)
	}
	before := ft.row(t)
	cuesBefore := rows(t, db, "SELECT * FROM djmdCue ORDER BY ID")
	listsBefore := rows(t, db, "SELECT * FROM djmdSongPlaylist ORDER BY ID")
	usnBefore := usn(t, db)
	countBefore := len(rows(t, db, "SELECT ID FROM djmdContent"))
	db.Close() // Rekordbox is closed while the importer writes

	ft.refresh(t)
	rep, err := ft.im.Sync(false)
	if err != nil {
		t.Fatal(err)
	}
	if rep.Changed != 1 || len(rep.Updated) != 1 || rep.Updated[0] != ft.path ||
		len(rep.Imported) != 0 || rep.New != 0 {
		t.Fatalf("report %+v", rep)
	}

	after := ft.row(t)
	db = ft.db(t)
	defer db.Close()
	var changed []string
	for col := range before {
		if before[col] != after[col] {
			changed = append(changed, col)
		}
	}
	sort.Strings(changed)
	// The genre, the year and the comment changed on the server; the title,
	// artist and album did not. FileSize and rb_file_id follow the new file.
	want := []string{"Commnt", "FileSize", "GenreID", "ReleaseYear", "rb_file_id", "rb_local_usn",
		"updated_text"}
	if !slices.Equal(changed, want) {
		t.Fatalf("changed columns %v, want %v", changed, want)
	}
	if got := named(t, db, "djmdGenre", after["GenreID"]); got != "Tech House" {
		t.Errorf("genre %q: the server's value wins over Rekordbox's", got)
	}
	if after["ArtistID"] != "9001" {
		t.Error("the artist edited in Rekordbox was overwritten although the server did not change it")
	}
	if after["ReleaseYear"] != "2019" || after["Commnt"] != "warm-up" {
		t.Errorf("year %s, comment %s", after["ReleaseYear"], after["Commnt"])
	}
	info, _ := os.Stat(ft.path)
	if after["FileSize"] != strconv.FormatInt(info.Size(), 10) {
		t.Errorf("FileSize %s, file %d", after["FileSize"], info.Size())
	}
	probed, _ := audio.Probe(ft.path)
	if probed.FileID != 0 && after["rb_file_id"] != strconv.FormatUint(probed.FileID, 10) {
		t.Errorf("rb_file_id %s, file %d", after["rb_file_id"], probed.FileID)
	}
	newUSN := usn(t, db)
	if after["rb_local_usn"] != strconv.FormatInt(newUSN, 10) || newUSN <= usnBefore {
		t.Errorf("usn: row %s, registry %d (was %d)", after["rb_local_usn"], newUSN, usnBefore)
	}
	if !slices.EqualFunc(cuesBefore, rows(t, db, "SELECT * FROM djmdCue ORDER BY ID"), mapsEqual) {
		t.Error("cues changed")
	}
	if !slices.EqualFunc(listsBefore, rows(t, db, "SELECT * FROM djmdSongPlaylist ORDER BY ID"), mapsEqual) {
		t.Error("playlist entries changed")
	}
	if n := len(rows(t, db, "SELECT ID FROM djmdContent")); n != countBefore {
		t.Errorf("%d tracks, was %d", n, countBefore)
	}

	// What was written is now what this computer has seen.
	st, _ := ledger.ReadFetched(ft.im.Home)
	if got := st.Tracks[ft.id].Tags; got == nil || got.Genre != "Tech House" || got.Year != 2019 {
		t.Errorf("remembered tags %+v", got)
	}
	// And the next sync has nothing to do.
	if rep, err := ft.im.Sync(false); err != nil || rep.Changed != 0 || len(rep.Updated) != 0 {
		t.Fatalf("second sync: %+v, %v", rep, err)
	}
}

func mapsEqual(a, b map[string]string) bool {
	if len(a) != len(b) {
		return false
	}
	for k, v := range a {
		if b[k] != v {
			return false
		}
	}
	return true
}

func TestNothingIsUpdatedWhileRekordboxRuns(t *testing.T) {
	ft := newFetchedTrack(t)
	before := ft.row(t)
	ft.refresh(t)
	ft.running = true
	dbPath := filepath.Join(ft.rbDir, "master.db")
	stamp, _ := os.Stat(dbPath)
	rep, err := ft.im.Sync(false)
	if !errors.Is(err, ErrRekordboxRunning) || !rep.Deferred {
		t.Fatalf("want deferral: %+v, %v", rep, err)
	}
	if now, _ := os.Stat(dbPath); !now.ModTime().Equal(stamp.ModTime()) {
		t.Error("master.db was touched while Rekordbox ran")
	}
	if !mapsEqual(before, ft.row(t)) {
		t.Fatal("the row changed while Rekordbox ran")
	}
	ft.running = false
	if rep, err := ft.im.Sync(false); err != nil || len(rep.Updated) != 1 {
		t.Fatalf("after Rekordbox closed: %+v, %v", rep, err)
	}
}

func TestTheBackupIsRestoredWhenTheCheckFails(t *testing.T) {
	ft := newFetchedTrack(t)
	before := ft.row(t)
	ft.refresh(t)
	quickCheck = func(*library.DB) error { return errors.New("integrity check failed: page 3") }
	t.Cleanup(func() { quickCheck = (*library.DB).QuickCheck })
	if _, err := ft.im.Sync(false); err == nil {
		t.Fatal("a failed check must fail the sync")
	}
	if !mapsEqual(before, ft.row(t)) {
		t.Fatalf("master.db was not restored: %v, now %v", before, ft.row(t))
	}
	// Nothing was marked: the next sync tries again.
	quickCheck = (*library.DB).QuickCheck
	if rep, err := ft.im.Sync(false); err != nil || len(rep.Updated) != 1 {
		t.Fatalf("retry: %+v, %v", rep, err)
	}
}

func TestAChangedTrackRemovedFromRekordboxIsNotImportedAgain(t *testing.T) {
	ft := newFetchedTrack(t)
	db := ft.db(t)
	if _, err := db.Exec("DELETE FROM djmdContent WHERE ID = ?", ft.contentID); err != nil {
		t.Fatal(err)
	}
	db.Close()
	ft.refresh(t)
	rep, err := ft.im.Sync(false)
	if err != nil || len(rep.Imported) != 0 || len(rep.Updated) != 0 || len(rep.NoRow) != 1 {
		t.Fatalf("report %+v, %v", rep, err)
	}
	if n := ft.count(t, "SELECT count(*) FROM djmdContent WHERE FileNameL = 'Night Drive.mp3'"); n != 0 {
		t.Fatal("re-imported")
	}
	if rep, _ := ft.im.Sync(false); rep.Changed != 0 || rep.New != 0 {
		t.Fatalf("not marked handled: %+v", rep)
	}
}

// A track the server removed after its newer copy arrived is not updated: its
// tombstone counts, and only the "removed on server" playlist hears of it.
func TestATrackWithATombstoneIsNotUpdated(t *testing.T) {
	ft := newFetchedTrack(t)
	before := ft.row(t)
	ft.refresh(t)
	st, err := ledger.ReadFetched(ft.im.Home)
	if err != nil {
		t.Fatal(err)
	}
	st.Removed[ft.id] = ledger.Tombstone{Path: "Night Drive.mp3", At: time.Now(), Reason: "deleted"}
	ledgertest.Save(t, ft.im.Home, st)
	rep, err := ft.im.Sync(false)
	if err != nil || rep.Changed != 0 || len(rep.Updated) != 0 || len(rep.MarkedRemoved) != 1 {
		t.Fatalf("%+v, %v", rep, err)
	}
	after := ft.row(t)
	for _, col := range []string{"GenreID", "ReleaseYear", "Commnt", "FileSize", "rb_file_id"} {
		if before[col] != after[col] {
			t.Errorf("%s changed: %s -> %s", col, before[col], after[col])
		}
	}
}

// The DJ's own edit of a fetched file (Mp3tag, say) did not come from the
// server: nothing is written to Rekordbox for it.
func TestALocalEditOfAFetchedFileIsLeftAlone(t *testing.T) {
	ft := newFetchedTrack(t)
	before := ft.row(t)
	ft.place(t, onServerAfter, time.Now().Add(-30*time.Minute))
	rep, err := ft.im.Sync(false)
	if err != nil || rep.Changed != 0 || len(rep.Updated) != 0 {
		t.Fatalf("%+v, %v", rep, err)
	}
	if !mapsEqual(before, ft.row(t)) {
		t.Fatal("a change that did not come from the server reached Rekordbox")
	}
}

// A newer copy that arrives before the first sync of this version is not lost
// when that sync widens state.json to the file as it is now.
func TestANewerCopyIsNotLostWhenTheStateIsWidened(t *testing.T) {
	ft := newFetchedTrack(t)
	ft.refresh(t)
	key := track.PathKey(ft.path)
	seen, err := ledger.ReadSynced(ft.im.Home)
	if err != nil {
		t.Fatal(err)
	}
	seen.Seen[key] = ledger.Handled{At: seen.Seen[key].At} // as an older companion left it
	ledgertest.Save(t, ft.im.Home, seen)
	if rep, err := ft.im.Sync(false); err != nil || len(rep.Updated) != 1 {
		t.Fatalf("%+v, %v", rep, err)
	}
	if got := ft.row(t)["ReleaseYear"]; got != "2019" {
		t.Fatalf("ReleaseYear %s", got)
	}
}

// A handled file that changes in a folder no fetch fills (a sync client's)
// is left alone in this version: local mode and synced folders come later.
func TestAChangeWithoutAFetchedTrackIsLeftAlone(t *testing.T) {
	e := newEnv(t)
	path := e.add(t, "synced.mp3")
	if _, err := e.im.Sync(false); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(path, tracktest.MP3(3, onServerAfter), 0o644)
	old := time.Now().Add(-time.Minute)
	os.Chtimes(path, old, old)
	dbPath := filepath.Join(e.rbDir, "master.db")
	stamp, _ := os.Stat(dbPath)
	rep, err := e.im.Sync(false)
	if err != nil || rep.Changed != 0 || len(rep.Updated) != 0 {
		t.Fatalf("%+v, %v", rep, err)
	}
	if now, _ := os.Stat(dbPath); !now.ModTime().Equal(stamp.ModTime()) {
		t.Error("master.db was opened for a change it does not act on")
	}
}

// While a fetch holds the lock, fetched.json may change under the importer:
// changed tracks wait for the next sync; new ones are still imported.
func TestChangedTracksWaitWhileAFetchRuns(t *testing.T) {
	ft := newFetchedTrack(t)
	ft.refresh(t)
	lock, err := ledger.LockFetch(ft.im.Home)
	if err != nil {
		t.Fatal(err)
	}
	ft.add(t, "brand new.mp3")
	rep, err := ft.im.Sync(false)
	lock.Unlock()
	if err != nil || len(rep.Imported) != 1 || len(rep.Updated) != 0 {
		t.Fatalf("%+v, %v", rep, err)
	}
	if rep, err := ft.im.Sync(false); err != nil || len(rep.Updated) != 1 {
		t.Fatalf("after the fetch: %+v, %v", rep, err)
	}
}

func TestDryRunListsUpdatesAndWritesNothing(t *testing.T) {
	ft := newFetchedTrack(t)
	before := ft.row(t)
	ft.refresh(t)
	rep, err := ft.im.Sync(true)
	if err != nil || len(rep.Updated) != 1 {
		t.Fatalf("%+v, %v", rep, err)
	}
	if !mapsEqual(before, ft.row(t)) {
		t.Fatal("a dry run wrote")
	}
	if rep, _ := ft.im.Sync(true); len(rep.Updated) != 1 {
		t.Fatal("a dry run marked the change handled")
	}
}
