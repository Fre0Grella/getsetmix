package library_test

import (
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/library/librarytest"
	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

// An empty title is written as the file name, as an import does; a year or
// comment cleared on the server is cleared in the row; a path with no row is
// reported, not imported.
func TestUpdateClearsAndReportsMissingRows(t *testing.T) {
	t.Parallel()
	dir, existing := setup(t)
	db, err := library.Open(filepath.Join(dir, "master.db"))
	if err != nil {
		t.Fatal(err)
	}
	other := "C:/Users/dj/Nextcloud/Music/not in rekordbox.mp3"
	res, err := db.Update([]library.Change{
		// The row is found however the folder's case is written.
		{Path: filepath.FromSlash(strings.Replace(existing, "Nextcloud/Music", "NEXTCLOUD/music", 1)),
			Tags:   track.Tags{},
			Fields: []string{"title", "year", "comment", "genre"}, FileSize: 1234},
		{Path: other, Fields: track.AllFields, FileSize: 1},
	}, now)
	if err != nil {
		t.Fatal(err)
	}
	if err := db.QuickCheck(); err != nil {
		t.Fatal(err)
	}
	db.Close()
	if len(res.Updated) != 1 || !slices.Equal(res.Missing, []string{other}) {
		t.Fatalf("result %+v", res)
	}
	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	var title, artist string
	var year, comment, genre, fileID any
	var size, usn int64
	if err := raw.QueryRow(`SELECT Title, ArtistID, ReleaseYear, Commnt, GenreID, FileSize, rb_file_id,
		rb_local_usn FROM djmdContent WHERE ID = ?`, librarytest.ExistingID).
		Scan(&title, &artist, &year, &comment, &genre, &size, &fileID, &usn); err != nil {
		t.Fatal(err)
	}
	if title != "La Plena - W Sound" || artist != "756733270" || year != nil || comment != nil ||
		genre != nil || size != 1234 || fileID != nil || usn != librarytest.StartUSN+1 {
		t.Fatalf("row: %q %q %v %v %v %d %v %d", title, artist, year, comment, genre, size, fileID, usn)
	}
	var registry int64
	raw.QueryRow("SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'").Scan(&registry)
	if registry != librarytest.StartUSN+1 {
		t.Fatalf("localUpdateCount %d", registry)
	}
}
