package library

import (
	"crypto/rand"
	"database/sql"
	"encoding/binary"
	"errors"
	"fmt"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// FileType codes of djmdContent.FileType.
const (
	FileMP3  = 1
	FileM4A  = 4
	FileFLAC = 5
	FileALAC = 6
	FileWAV  = 11
	FileAIFF = 12
)

// Track is one audio file to add to the collection.
type Track struct {
	Path    string // absolute path on this machine
	Title   string
	Artist  string
	Album   string
	Genre   string
	Comment string
	Year    int
	TrackNo int

	FileType   int
	FileSize   int64
	FileID     uint64 // filesystem identity: NTFS file ID / inode, as Rekordbox stores it
	Length     int    // seconds
	BitRate    int    // kbps
	BitDepth   int
	SampleRate int
}

// Playlist identifies the playlist new tracks are appended to.
type Playlist struct {
	ID        string
	Created   bool // false when it already existed
	UpdatedAt time.Time
}

// Result of an Import.
type Result struct {
	Added    []string // paths written to the collection
	Skipped  []string // paths that were already in the collection
	Playlist Playlist
}

// Import adds tracks to the collection and appends them to the root-level
// playlist named playlistName (created when missing), in one transaction.
// Tracks whose path is already in the collection are skipped, never doubled.
func (d *DB) Import(tracks []Track, playlistName string, now time.Time) (Result, error) {
	var res Result
	tx, err := d.sql.Begin()
	if err != nil {
		return res, err
	}
	defer tx.Rollback() //nolint:errcheck // no-op after Commit

	w := &writer{tx: tx, now: stamp(now), date: now.Local().Format("2006-01-02"), cache: map[string]string{}}
	if err := w.loadContext(); err != nil {
		return res, err
	}

	known := map[string]bool{}
	rows, err := tx.Query("SELECT FolderPath FROM djmdContent WHERE rb_local_deleted = 0 AND FolderPath IS NOT NULL")
	if err != nil {
		return res, err
	}
	for rows.Next() {
		var p string
		if err := rows.Scan(&p); err != nil {
			rows.Close()
			return res, err
		}
		known[PathKey(p)] = true
	}
	rows.Close()

	var added []string // content IDs, in import order
	for _, t := range tracks {
		key := PathKey(t.Path)
		if known[key] {
			res.Skipped = append(res.Skipped, t.Path)
			continue
		}
		id, err := w.addContent(t)
		if err != nil {
			return res, fmt.Errorf("%s: %w", filepath.Base(t.Path), err)
		}
		known[key] = true
		added = append(added, id)
		res.Added = append(res.Added, t.Path)
	}

	if len(added) > 0 {
		pl, err := w.ensurePlaylist(playlistName)
		if err != nil {
			return res, err
		}
		if err := w.appendToPlaylist(pl.ID, added); err != nil {
			return res, err
		}
		pl.UpdatedAt = now
		res.Playlist = pl
		if _, err := tx.Exec(
			"UPDATE agentRegistry SET int_1 = ? WHERE registry_id = 'localUpdateCount'", w.usn); err != nil {
			return res, err
		}
	}
	if err := tx.Commit(); err != nil {
		return res, err
	}
	return res, nil
}

// writer holds the per-import state: the running USN and the IDs every new
// row has to point at.
type writer struct {
	tx    *sql.Tx
	now   string // created_at / updated_at
	date  string // DateCreated / StockDate (local calendar day, like Rekordbox)
	usn   int64
	cache map[string]string // "table\x00name" -> ID

	deviceID    string
	masterDBID  string
	contentLink sql.NullInt64
}

// nextUSN mirrors Rekordbox's change counter: every row we touch gets the
// next value, and agentRegistry.localUpdateCount ends at the last one.
func (w *writer) nextUSN() int64 {
	w.usn++
	return w.usn
}

func (w *writer) loadContext() error {
	err := w.tx.QueryRow(
		"SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'").Scan(&w.usn)
	if err != nil {
		return fmt.Errorf("reading localUpdateCount: %w", err)
	}

	// The local device: djmdProperty names it; fall back to the device most
	// tracks belong to (there can be others, e.g. a USB stick's).
	_ = w.tx.QueryRow("SELECT DeviceID FROM djmdProperty LIMIT 1").Scan(&w.deviceID)
	if w.deviceID == "" {
		_ = w.tx.QueryRow(`SELECT DeviceID FROM djmdContent WHERE DeviceID IS NOT NULL
			GROUP BY DeviceID ORDER BY count(*) DESC LIMIT 1`).Scan(&w.deviceID)
	}
	if w.deviceID == "" {
		return errors.New("cannot tell which device is this computer (djmdDevice)")
	}
	if err := w.tx.QueryRow("SELECT MasterDBID FROM djmdDevice WHERE ID = ?", w.deviceID).
		Scan(&w.masterDBID); err != nil {
		return fmt.Errorf("device %s: %w", w.deviceID, err)
	}

	// ContentLink: copy what Rekordbox put on the most recent local import.
	// Only on an empty library fall back to the TRACK menu item's USN, which
	// is what pyrekordbox uses.
	err = w.tx.QueryRow(`SELECT ContentLink FROM djmdContent
		WHERE DeviceID = ? AND ContentLink IS NOT NULL ORDER BY created_at DESC LIMIT 1`,
		w.deviceID).Scan(&w.contentLink)
	if errors.Is(err, sql.ErrNoRows) {
		_ = w.tx.QueryRow("SELECT rb_local_usn FROM djmdMenuItems WHERE Name = 'TRACK'").Scan(&w.contentLink)
	}
	return nil
}

func (w *writer) addContent(t Track) (string, error) {
	id, err := w.unusedID("djmdContent", "ID", 28)
	if err != nil {
		return "", err
	}
	artistID, err := w.ensureNamed("djmdArtist", t.Artist)
	if err != nil {
		return "", err
	}
	albumID, err := w.ensureNamed("djmdAlbum", t.Album)
	if err != nil {
		return "", err
	}
	genreID, err := w.ensureNamed("djmdGenre", t.Genre)
	if err != nil {
		return "", err
	}
	fileID := sql.NullString{}
	if t.FileID != 0 {
		fileID = sql.NullString{String: strconv.FormatUint(t.FileID, 10), Valid: true}
	}
	title := t.Title
	if title == "" {
		title = trimExt(filepath.Base(t.Path))
	}
	_, err = w.tx.Exec(`INSERT INTO djmdContent (
		ID, FolderPath, FileNameL, FileNameS, Title, ArtistID, AlbumID, GenreID,
		Length, TrackNo, BitRate, BitDepth, Commnt, FileType, ReleaseYear,
		StockDate, MasterDBID, MasterSongID, FileSize, SampleRate, DateCreated,
		ContentLink, HotCueAutoLoad, DeliveryControl, ServiceID, OrgFolderPath,
		ExtInfo, rb_file_id, DeviceID, UUID,
		rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
		rb_local_usn, created_at, updated_at
	) VALUES (?,?,?,'',?,?,?,?, ?,?,?,?,?,?,?, ?,?,?,?,?,?, ?,'on','on',0,'', 'null',?,?,?, 0,0,0,0, ?,?,?)`,
		id, FolderPath(t.Path), filepath.Base(t.Path), title, artistID, albumID, genreID,
		nullInt(t.Length), nullInt(t.TrackNo), nullInt(t.BitRate), nullInt(t.BitDepth),
		nullStr(t.Comment), t.FileType, nullInt(t.Year),
		w.date, w.masterDBID, id, t.FileSize, nullInt(t.SampleRate), w.date,
		w.contentLink, fileID, w.deviceID, newUUID(),
		w.nextUSN(), w.now, w.now)
	return id, err
}

// ensureNamed returns the ID of the artist/album/genre called name, creating
// it when missing. Rekordbox matches these by exact name.
func (w *writer) ensureNamed(table, name string) (sql.NullString, error) {
	if name == "" {
		return sql.NullString{}, nil
	}
	key := table + "\x00" + name
	if id, ok := w.cache[key]; ok {
		return sql.NullString{String: id, Valid: true}, nil
	}
	var id string
	err := w.tx.QueryRow("SELECT ID FROM "+table+" WHERE Name = ? AND rb_local_deleted = 0 LIMIT 1", name).Scan(&id)
	switch {
	case errors.Is(err, sql.ErrNoRows):
		if id, err = w.unusedID(table, "ID", 32); err != nil {
			return sql.NullString{}, err
		}
		cols, vals := "ID, Name, UUID", []any{id, name, newUUID()}
		if table == "djmdAlbum" {
			cols, vals = cols+", Compilation", append(vals, 0)
		}
		placeholders := strings.TrimSuffix(strings.Repeat("?, ", len(vals)), ", ")
		vals = append(vals, w.nextUSN(), w.now, w.now)
		_, err = w.tx.Exec("INSERT INTO "+table+" ("+cols+", rb_data_status, rb_local_data_status,"+
			" rb_local_deleted, rb_local_synced, rb_local_usn, created_at, updated_at)"+
			" VALUES ("+placeholders+", 0, 0, 0, 0, ?, ?, ?)", vals...)
		if err != nil {
			return sql.NullString{}, err
		}
	case err != nil:
		return sql.NullString{}, err
	}
	w.cache[key] = id
	return sql.NullString{String: id, Valid: true}, nil
}

func (w *writer) ensurePlaylist(name string) (Playlist, error) {
	var pl Playlist
	err := w.tx.QueryRow(`SELECT ID FROM djmdPlaylist
		WHERE Name = ? AND ParentID = 'root' AND Attribute = 0 AND rb_local_deleted = 0
		ORDER BY Seq LIMIT 1`, name).Scan(&pl.ID)
	if err == nil {
		return pl, nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return pl, err
	}
	if pl.ID, err = w.unusedID("djmdPlaylist", "ID", 32); err != nil {
		return pl, err
	}
	var seq int
	if err := w.tx.QueryRow(`SELECT coalesce(max(Seq), 0) + 1 FROM djmdPlaylist
		WHERE ParentID = 'root' AND rb_local_deleted = 0`).Scan(&seq); err != nil {
		return pl, err
	}
	_, err = w.tx.Exec(`INSERT INTO djmdPlaylist (ID, Seq, Name, Attribute, ParentID, UUID,
		rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
		rb_local_usn, created_at, updated_at) VALUES (?, ?, ?, 0, 'root', ?, 0, 0, 0, 0, ?, ?, ?)`,
		pl.ID, seq, name, newUUID(), w.nextUSN(), w.now, w.now)
	pl.Created = true
	return pl, err
}

func (w *writer) appendToPlaylist(playlistID string, contentIDs []string) error {
	var last int
	if err := w.tx.QueryRow(`SELECT coalesce(max(TrackNo), 0) FROM djmdSongPlaylist
		WHERE PlaylistID = ? AND rb_local_deleted = 0`, playlistID).Scan(&last); err != nil {
		return err
	}
	for i, cid := range contentIDs {
		_, err := w.tx.Exec(`INSERT INTO djmdSongPlaylist (ID, PlaylistID, ContentID, TrackNo, UUID,
			rb_data_status, rb_local_data_status, rb_local_deleted, rb_local_synced,
			rb_local_usn, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0, ?, ?, ?)`,
			newUUID(), playlistID, cid, last+i+1, newUUID(), w.nextUSN(), w.now, w.now)
		if err != nil {
			return err
		}
	}
	_, err := w.tx.Exec("UPDATE djmdPlaylist SET updated_at = ?, rb_local_usn = ? WHERE ID = ?",
		w.now, w.nextUSN(), playlistID)
	return err
}

// unusedID draws random IDs the way Rekordbox does (28-bit for tracks,
// 32-bit elsewhere — both visible in real libraries) until one is free.
func (w *writer) unusedID(table, column string, bits uint) (string, error) {
	for range 1000 {
		var b [4]byte
		if _, err := rand.Read(b[:]); err != nil {
			return "", err
		}
		n := binary.BigEndian.Uint32(b[:]) >> (32 - bits)
		if n < 100 {
			continue
		}
		id := strconv.FormatUint(uint64(n), 10)
		var exists int
		if err := w.tx.QueryRow("SELECT count(*) FROM "+table+" WHERE "+column+" = ?", id).
			Scan(&exists); err != nil {
			return "", err
		}
		if exists == 0 {
			return id, nil
		}
	}
	return "", fmt.Errorf("no free ID in %s", table)
}

func newUUID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	b[6] = b[6]&0x0f | 0x40
	b[8] = b[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func nullInt(n int) sql.NullInt64 {
	return sql.NullInt64{Int64: int64(n), Valid: n > 0}
}

func nullStr(s string) sql.NullString {
	return sql.NullString{String: s, Valid: s != ""}
}

func trimExt(name string) string {
	return name[:len(name)-len(filepath.Ext(name))]
}
