package library_test

import (
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/library/librarytest"
)

var now = time.Date(2026, 10, 17, 14, 3, 7, 123_000_000, time.UTC)

func setup(t *testing.T) (dir, existing string) {
	t.Helper()
	dir = t.TempDir()
	existing = "C:/Users/dj/Nextcloud/Music/La Plena - W Sound.mp3"
	librarytest.New(t, dir, existing)
	return dir, existing
}

func track(path string) library.Track {
	return library.Track{
		Path: path, Title: "Ella Me Levantó", Artist: "Daddy Yankee", Album: "Barrio Fino",
		Genre: "Reggaeton", Comment: "https://youtu.be/x", FileType: library.FileMP3,
		FileSize: 8472296, FileID: 0xF0000001F9DA4, Length: 209, BitRate: 320,
		BitDepth: 16, SampleRate: 44100,
	}
}

func TestImportWritesRowsLikeRekordbox(t *testing.T) {
	dir, _ := setup(t)
	db, err := library.Open(filepath.Join(dir, "master.db"))
	if err != nil {
		t.Fatal(err)
	}
	// Native separators in, forward slashes stored (a no-op off Windows).
	path := filepath.FromSlash("C:/Users/dj/Nextcloud/Music/Ella Me Levantó - Daddy Yankee.mp3")
	res, err := db.Import([]library.Track{track(path)}, "GetSetMix", now)
	if err != nil {
		t.Fatal(err)
	}
	if err := db.QuickCheck(); err != nil {
		t.Fatal(err)
	}
	db.Close()
	if len(res.Added) != 1 || !res.Playlist.Created {
		t.Fatalf("result = %+v", res)
	}

	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	var (
		id, folder, fileName, title, deviceID, masterDBID, masterSongID, fileID string
		stock, created, updated, artist, album, genre                           string
		contentLink, usn, fileType, length                                      int64
	)
	err = raw.QueryRow(`SELECT c.ID, FolderPath, FileNameL, Title, DeviceID, MasterDBID, MasterSongID,
		rb_file_id, StockDate, CAST(c.created_at AS TEXT), CAST(c.updated_at AS TEXT),
		a.Name, al.Name, g.Name, ContentLink, c.rb_local_usn, FileType, Length
		FROM djmdContent c JOIN djmdArtist a ON a.ID = c.ArtistID
		JOIN djmdAlbum al ON al.ID = c.AlbumID JOIN djmdGenre g ON g.ID = c.GenreID
		WHERE c.Title = 'Ella Me Levantó'`).Scan(&id, &folder, &fileName, &title, &deviceID,
		&masterDBID, &masterSongID, &fileID, &stock, &created, &updated, &artist, &album, &genre,
		&contentLink, &usn, &fileType, &length)
	if err != nil {
		t.Fatal(err)
	}
	checks := map[string][2]any{
		"FolderPath uses forward slashes":   {folder, "C:/Users/dj/Nextcloud/Music/Ella Me Levantó - Daddy Yankee.mp3"},
		"FileNameL":                         {fileName, "Ella Me Levantó - Daddy Yankee.mp3"},
		"local device, not the USB one":     {deviceID, librarytest.DeviceID},
		"MasterDBID of that device":         {masterDBID, librarytest.MasterDBID},
		"MasterSongID = ID":                 {masterSongID, id},
		"rb_file_id is the file ID":         {fileID, "4222124652731812"},
		"ContentLink copied from Rekordbox": {contentLink, int64(librarytest.ContentLink)},
		"created_at layout":                 {created, "2026-10-17 14:03:07.123 +00:00"},
		"artist":                            {artist, "Daddy Yankee"},
		"album":                             {album, "Barrio Fino"},
		"genre":                             {genre, "Reggaeton"},
		"FileType":                          {fileType, int64(library.FileMP3)},
		"Length":                            {length, int64(209)},
	}
	for name, c := range checks {
		if c[0] != c[1] {
			t.Errorf("%s: got %v, want %v", name, c[0], c[1])
		}
	}
	if n, _ := strconv.Atoi(id); n >= 1<<28 || n < 100 {
		t.Errorf("track ID %s is not a 28-bit ID", id)
	}

	// USN bookkeeping: every new row got a fresh USN above the old counter,
	// and the counter ends on the highest one.
	var counter, maxUSN int64
	raw.QueryRow("SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'").Scan(&counter)
	raw.QueryRow(`SELECT max(u) FROM (SELECT rb_local_usn u FROM djmdContent UNION ALL
		SELECT rb_local_usn FROM djmdArtist UNION ALL SELECT rb_local_usn FROM djmdAlbum UNION ALL
		SELECT rb_local_usn FROM djmdGenre UNION ALL SELECT rb_local_usn FROM djmdPlaylist UNION ALL
		SELECT rb_local_usn FROM djmdSongPlaylist)`).Scan(&maxUSN)
	if usn <= librarytest.StartUSN || counter != maxUSN {
		t.Errorf("usn %d, counter %d, max row usn %d", usn, counter, maxUSN)
	}

	var plName, parent string
	var seq, trackNo int
	err = raw.QueryRow(`SELECT p.Name, p.ParentID, p.Seq, s.TrackNo FROM djmdSongPlaylist s
		JOIN djmdPlaylist p ON p.ID = s.PlaylistID WHERE s.ContentID = ?`, id).Scan(&plName, &parent, &seq, &trackNo)
	if err != nil {
		t.Fatal(err)
	}
	if plName != "GetSetMix" || parent != "root" || seq != 2 || trackNo != 1 {
		t.Errorf("playlist row: %s %s seq=%d track=%d", plName, parent, seq, trackNo)
	}
}

func TestImportReusesNamesAndSkipsKnownPaths(t *testing.T) {
	dir, existing := setup(t)
	db, err := library.Open(filepath.Join(dir, "master.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	a := track("/Users/dj/Music/a.mp3")
	a.Artist = "W Sound" // already in the library
	b := track("/Users/dj/Music/b.mp3")
	b.Artist = "W Sound"
	dup := track(strings.ToUpper(existing)) // same file, different case
	res, err := db.Import([]library.Track{a, b, dup}, "GetSetMix", now)
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Added) != 2 || len(res.Skipped) != 1 {
		t.Fatalf("added %v skipped %v", res.Added, res.Skipped)
	}

	// Second import into the same playlist appends after the first two.
	c := track("/Users/dj/Music/c.mp3")
	res2, err := db.Import([]library.Track{c, a}, "GetSetMix", now.Add(time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	if res2.Playlist.Created || res2.Playlist.ID != res.Playlist.ID || len(res2.Skipped) != 1 {
		t.Fatalf("second import: %+v", res2)
	}
	db.Close()

	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	var artists, songs, maxTrack int
	raw.QueryRow("SELECT count(*) FROM djmdArtist WHERE Name = 'W Sound'").Scan(&artists)
	raw.QueryRow("SELECT count(*), max(TrackNo) FROM djmdSongPlaylist WHERE PlaylistID = ?",
		res.Playlist.ID).Scan(&songs, &maxTrack)
	if artists != 1 || songs != 3 || maxTrack != 3 {
		t.Errorf("artists=%d songs=%d maxTrack=%d", artists, songs, maxTrack)
	}
}

func TestDominantFolder(t *testing.T) {
	dir, _ := setup(t)
	db, err := library.OpenReadOnly(filepath.Join(dir, "master.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	got, err := db.DominantFolder()
	if err != nil || filepath.ToSlash(got) != "C:/Users/dj/Nextcloud/Music" {
		t.Fatalf("got %q, %v", got, err)
	}
}

func TestOpenRejectsAPlainSQLiteFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "master.db")
	os.WriteFile(path, []byte("SQLite format 3\x00 but not really"), 0o644)
	if _, err := library.OpenReadOnly(path); err == nil {
		t.Fatal("expected an error")
	}
}

func TestPlaylistXML(t *testing.T) {
	dir, _ := setup(t)
	path := filepath.Join(dir, "masterPlaylists6.xml")
	created := library.Playlist{ID: "2880967891", Created: true, UpdatedAt: now}
	if err := library.SyncPlaylistXML(path, created); err != nil {
		t.Fatal(err)
	}
	data, _ := os.ReadFile(path)
	want := `    <NODE Id="ABB814D3" ParentId="0" Attribute="0" Timestamp="` +
		strconv.FormatInt(now.UnixMilli(), 10) + `" Lib_Type="0" CheckType="0"/>`
	if !strings.Contains(string(data), want+"\n  </PLAYLISTS>") {
		t.Fatalf("node not appended:\n%s", data)
	}
	if !strings.HasPrefix(string(data), librarytest.PlaylistXML[:200]) {
		t.Fatal("existing content was rewritten")
	}

	// A later sync refreshes the Timestamp in place.
	later := created
	later.Created, later.UpdatedAt = false, now.Add(time.Hour)
	if err := library.SyncPlaylistXML(path, later); err != nil {
		t.Fatal(err)
	}
	data, _ = os.ReadFile(path)
	nodes := regexp.MustCompile(`Id="ABB814D3"[^>]*Timestamp="(\d+)"`).FindAllStringSubmatch(string(data), -1)
	if len(nodes) != 1 || nodes[0][1] != strconv.FormatInt(later.UpdatedAt.UnixMilli(), 10) {
		t.Fatalf("timestamp not refreshed: %v", nodes)
	}
}

func TestPathKey(t *testing.T) {
	nfd := "Bee\u0301le.mp3" // macOS hands out decomposed names
	if library.PathKey(filepath.FromSlash("C:/Music/BEÉLE.mp3")) != library.PathKey("c:/music/"+nfd) {
		t.Fatal("path keys should match across slashes, case and normalisation")
	}
}

func TestOpenPathWithURIMetacharacters(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "DJ #1 100%")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	librarytest.New(t, dir, "/x/a.mp3")
	db, err := library.OpenReadOnly(filepath.Join(dir, "master.db"))
	if err != nil {
		t.Fatal(err)
	}
	db.Close()
}
