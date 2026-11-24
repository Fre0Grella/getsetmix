package library_test

import (
	"database/sql"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/library/librarytest"
)

// removedSetup is a collection of three imported tracks; the first has a hot
// cue and sits in a playlist of the DJ's own.
func removedSetup(t *testing.T) (dir string, paths []string) {
	t.Helper()
	dir, _ = setup(t)
	paths = []string{"/Users/dj/Music/a.mp3", "/Users/dj/Music/b.mp3", "/Users/dj/Music/c.mp3"}
	db, err := library.Open(filepath.Join(dir, "master.db"))
	if err != nil {
		t.Fatal(err)
	}
	var tracks []library.Track
	for _, p := range paths {
		tracks = append(tracks, track(p))
	}
	if _, err := db.Import(tracks, "GetSetMix", now); err != nil {
		t.Fatal(err)
	}
	db.Close()
	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	id := contentID(t, raw, paths[0])
	for _, q := range []string{
		`INSERT INTO djmdCue (ID, ContentID, InMsec, Kind, created_at, updated_at) VALUES ('cue1', ?, 32000, 1, 'x', 'x')`,
		`INSERT INTO djmdSongPlaylist (ID, PlaylistID, ContentID, TrackNo, created_at, updated_at) VALUES ('mine1', '200000', ?, 1, 'x', 'x')`,
	} {
		if _, err := raw.Exec(q, id); err != nil {
			t.Fatal(err)
		}
	}
	return dir, paths
}

func contentID(t *testing.T, raw *sql.DB, path string) string {
	t.Helper()
	var id string
	if err := raw.QueryRow("SELECT ID FROM djmdContent WHERE FolderPath = ?", path).Scan(&id); err != nil {
		t.Fatal(err)
	}
	return id
}

// removedList is the removed playlist, as content IDs in TrackNo order.
func removedList(t *testing.T, raw *sql.DB) []string {
	t.Helper()
	rows, err := raw.Query(`SELECT s.ContentID, s.TrackNo FROM djmdSongPlaylist s
		JOIN djmdPlaylist p ON p.ID = s.PlaylistID WHERE p.Name = ? ORDER BY s.TrackNo`, library.RemovedPlaylist)
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()
	var ids []string
	for i := 1; rows.Next(); i++ {
		var id string
		var no int
		rows.Scan(&id, &no)
		if no != i {
			t.Errorf("TrackNo %d at position %d", no, i)
		}
		ids = append(ids, id)
	}
	return ids
}

func markRemoved(t *testing.T, dir string, add, drop []string, at time.Time) library.RemovedResult {
	t.Helper()
	db, err := library.Open(filepath.Join(dir, "master.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	res, err := db.MarkRemoved(add, drop, at)
	if err != nil {
		t.Fatal(err)
	}
	if err := db.QuickCheck(); err != nil {
		t.Fatal(err)
	}
	return res
}

func TestMarkRemovedListsATrackOnceAndKeepsEverythingElse(t *testing.T) {
	dir, paths := removedSetup(t)
	before := librarytest.Open(t, filepath.Join(dir, "master.db"))
	var contentBefore, songsBefore int
	before.QueryRow("SELECT count(*) FROM djmdContent").Scan(&contentBefore)
	before.QueryRow("SELECT count(*) FROM djmdSongPlaylist").Scan(&songsBefore)
	before.Close()

	res := markRemoved(t, dir, []string{paths[0], paths[2], "/Users/dj/Music/not in rekordbox.mp3"}, nil, now)
	if !reflect.DeepEqual(res.Added, []string{paths[0], paths[2]}) ||
		!reflect.DeepEqual(res.NotFound, []string{"/Users/dj/Music/not in rekordbox.mp3"}) ||
		!res.Playlist.Created || res.Playlist.ID == "" {
		t.Fatalf("result %+v", res)
	}
	// Again, and with the same path twice: nothing is listed twice.
	again := markRemoved(t, dir, []string{paths[0], paths[0]}, nil, now.Add(time.Minute))
	if len(again.Added) != 0 || len(again.Already) != 2 || again.Playlist.ID != "" {
		t.Fatalf("second time %+v", again)
	}

	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	a, c := contentID(t, raw, paths[0]), contentID(t, raw, paths[2])
	if got := removedList(t, raw); !reflect.DeepEqual(got, []string{a, c}) {
		t.Fatalf("removed playlist %v", got)
	}
	var contentAfter, songsAfter, cues, mine, parent int
	raw.QueryRow("SELECT count(*) FROM djmdContent").Scan(&contentAfter)
	raw.QueryRow("SELECT count(*) FROM djmdSongPlaylist").Scan(&songsAfter)
	raw.QueryRow("SELECT count(*) FROM djmdCue WHERE ContentID = ?", a).Scan(&cues)
	raw.QueryRow("SELECT count(*) FROM djmdSongPlaylist WHERE PlaylistID = '200000' AND ContentID = ?", a).Scan(&mine)
	raw.QueryRow("SELECT count(*) FROM djmdPlaylist WHERE Name = ? AND ParentID = 'root'", library.RemovedPlaylist).Scan(&parent)
	if contentAfter != contentBefore || songsAfter != songsBefore+2 || cues != 1 || mine != 1 || parent != 1 {
		t.Errorf("content %d->%d, songs %d->%d, cues %d, own playlist %d, removed playlists %d",
			contentBefore, contentAfter, songsBefore, songsAfter, cues, mine, parent)
	}
	var counter, maxUSN int64
	raw.QueryRow("SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'").Scan(&counter)
	raw.QueryRow(`SELECT max(u) FROM (SELECT rb_local_usn u FROM djmdPlaylist UNION ALL
		SELECT rb_local_usn FROM djmdSongPlaylist UNION ALL SELECT rb_local_usn FROM djmdContent)`).Scan(&maxUSN)
	if counter != maxUSN {
		t.Errorf("localUpdateCount %d, highest row usn %d", counter, maxUSN)
	}
}

func TestMarkRemovedTakesARestoredTrackOut(t *testing.T) {
	dir, paths := removedSetup(t)
	markRemoved(t, dir, paths, nil, now)
	res := markRemoved(t, dir, nil, []string{paths[0], "/Users/dj/Music/unknown.mp3"}, now.Add(time.Hour))
	if !reflect.DeepEqual(res.Dropped, []string{paths[0]}) || res.Playlist.ID == "" || res.Playlist.Created {
		t.Fatalf("result %+v", res)
	}
	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	a, b, c := contentID(t, raw, paths[0]), contentID(t, raw, paths[1]), contentID(t, raw, paths[2])
	if got := removedList(t, raw); !reflect.DeepEqual(got, []string{b, c}) {
		t.Fatalf("removed playlist %v, want %v", got, []string{b, c}) // renumbered from 1
	}
	var cues, mine, rows int
	raw.QueryRow("SELECT count(*) FROM djmdCue WHERE ContentID = ?", a).Scan(&cues)
	raw.QueryRow("SELECT count(*) FROM djmdSongPlaylist WHERE ContentID = ? AND PlaylistID = '200000'", a).Scan(&mine)
	raw.QueryRow("SELECT count(*) FROM djmdContent WHERE ID = ?", a).Scan(&rows)
	if cues != 1 || mine != 1 || rows != 1 {
		t.Errorf("cues %d, own playlist %d, row %d", cues, mine, rows)
	}
}

func TestMarkRemovedWithNothingToDoWritesNothing(t *testing.T) {
	dir, paths := removedSetup(t)
	res := markRemoved(t, dir, nil, paths, now) // no removed playlist yet
	if len(res.Dropped) != 0 || res.Playlist.ID != "" {
		t.Fatalf("%+v", res)
	}
	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	var n int
	raw.QueryRow("SELECT count(*) FROM djmdPlaylist WHERE Name = ?", library.RemovedPlaylist).Scan(&n)
	if n != 0 {
		t.Fatal("the playlist was created with nothing to list")
	}
}
