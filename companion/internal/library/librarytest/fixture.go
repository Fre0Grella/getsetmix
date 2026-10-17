// Package librarytest builds a throwaway Rekordbox library for tests: a
// SQLCipher master.db with Rekordbox 7's real schema (schema.sql was dumped
// from a Rekordbox 7.2 library — structure only, no rows) seeded the way a
// fresh install is, plus a masterPlaylists6.xml.
package librarytest

import (
	"database/sql"
	_ "embed"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"

	_ "github.com/mutecomm/go-sqlcipher/v4"
)

//go:embed schema.sql
var schema string

// Fixed identities the seed uses, for assertions.
const (
	DeviceID    = "38b21e70-897e-4dbb-856e-549006765292"
	MasterDBID  = "4243926847"
	USBDeviceID = "17f5245c-0000-17f5-245c-245cf610e892"
	ContentLink = 2885134
	StartUSN    = 75109
	ExistingID  = "36936338"
	PlaylistXML = `<?xml version="1.0" encoding="UTF-8"?>

<MASTER_PLAYLIST Version="3.0.0" AutomaticSync="0">
  <PRODUCT Name="rekordbox" Version="7.2.14" Company="Pioneer DJ"/>
  <PLAYLISTS>
    <NODE Id="30D40" ParentId="0" Attribute="0" Timestamp="0" Lib_Type="0" CheckType="0"/>
  </PLAYLISTS>
</MASTER_PLAYLIST>
`
)

// Key duplicates library.Key so this package has no import cycle.
const Key = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"

// New creates dir/master.db and dir/masterPlaylists6.xml. existing is the
// FolderPath of a track already in the collection.
func New(t testing.TB, dir, existing string) {
	t.Helper()
	db := Open(t, filepath.Join(dir, "master.db"))
	defer db.Close()
	exec := func(q string, args ...any) {
		t.Helper()
		if _, err := db.Exec(q, args...); err != nil {
			t.Fatalf("%v\n%s", err, q)
		}
	}
	for _, stmt := range strings.Split(schema, ";\n") {
		if strings.TrimSpace(stmt) != "" {
			exec(stmt)
		}
	}
	const ts = "2024-08-23 12:39:44.842 +00:00"
	exec("PRAGMA journal_mode=WAL")
	exec(`INSERT INTO agentRegistry (registry_id, int_1, created_at, updated_at)
		VALUES ('localUpdateCount', ?, ?, ?)`, StartUSN, ts, ts)
	exec(`INSERT INTO djmdProperty (DBID, DBVersion, DeviceID, created_at, updated_at)
		VALUES (?, '6000', ?, ?, ?)`, MasterDBID, DeviceID, ts, ts)
	// The USB device comes first on purpose: picking "the first device" is wrong.
	exec(`INSERT INTO djmdDevice (ID, MasterDBID, Name, created_at, updated_at)
		VALUES (?, '401941596', 'RE879EL1', ?, ?)`, USBDeviceID, ts, ts)
	exec(`INSERT INTO djmdDevice (ID, MasterDBID, Name, created_at, updated_at)
		VALUES (?, ?, 'FreoLaptop', ?, ?)`, DeviceID, MasterDBID, ts, ts)
	exec(`INSERT INTO djmdMenuItems (ID, Class, Name, rb_local_usn, created_at, updated_at)
		VALUES ('4', -125, 'TRACK', 35476, ?, ?)`, ts, ts)
	exec(`INSERT INTO djmdArtist (ID, Name, UUID, rb_local_usn, created_at, updated_at)
		VALUES ('756733270', 'W Sound', 'u-artist', 74000, ?, ?)`, ts, ts)
	exec(`INSERT INTO djmdContent (ID, FolderPath, FileNameL, Title, ArtistID, FileType,
		ContentLink, DeviceID, MasterDBID, MasterSongID, UUID, rb_local_usn, created_at, updated_at)
		VALUES (?, ?, ?, 'La Plena', '756733270', 1, ?, ?, ?, ?, 'u-content', 75096, ?, ?)`,
		ExistingID, existing, filepath.Base(existing), ContentLink, DeviceID, MasterDBID, ExistingID, ts, ts)
	exec(`INSERT INTO djmdPlaylist (ID, Seq, Name, Attribute, ParentID, UUID, rb_local_usn, created_at, updated_at)
		VALUES ('200000', 1, 'Playlist analisi CUE', 0, 'root', 'u-pl', 74480, ?, ?)`, ts, ts)
	if err := os.WriteFile(filepath.Join(dir, "masterPlaylists6.xml"), []byte(PlaylistXML), 0o644); err != nil {
		t.Fatal(err)
	}
}

// Open opens (creating if needed) an encrypted database for inspection.
func Open(t testing.TB, path string) *sql.DB {
	t.Helper()
	escaped := strings.NewReplacer("%", "%25", "?", "%3f", "#", "%23").Replace(filepath.ToSlash(path))
	db, err := sql.Open("sqlite3", "file:"+escaped+"?_pragma_key="+url.QueryEscape(Key))
	if err != nil {
		t.Fatal(err)
	}
	db.SetMaxOpenConns(1)
	return db
}
