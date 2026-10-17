// Package library reads and writes Rekordbox's own collection database.
//
// Rekordbox 6 and 7 keep the collection in master.db, a SQLCipher 4 database
// whose key is the same on every install (it has been public since
// pyrekordbox extracted it). Nothing here is guessed: every column we write
// mirrors what Rekordbox itself stores for a freshly imported track, checked
// against real rows, and every write goes through one transaction followed by
// an integrity check.
//
// Rekordbox must not be running while we write. It keeps master.db open in
// WAL mode for its whole session and does not expect anyone else to change it.
package library

import (
	"database/sql"
	"errors"
	"fmt"
	"net/url"
	"path/filepath"
	"strings"
	"time"

	_ "github.com/mutecomm/go-sqlcipher/v4" // registers the "sqlite3" driver
	"golang.org/x/text/unicode/norm"
)

// Key is the SQLCipher passphrase of every Rekordbox 6/7 master.db.
const Key = "402fd482c38817c35ffa8ffb8c7d93143b749e7d315df7a81732a1ff43608497"

// Timestamp layout of created_at/updated_at as Rekordbox writes them (UTC).
const timeLayout = "2006-01-02 15:04:05.000 -07:00"

// DB is an open master.db.
type DB struct {
	sql  *sql.DB
	Path string
}

// Open opens master.db read-write and proves the key works.
func Open(path string) (*DB, error) {
	return open(path, "")
}

// OpenReadOnly opens master.db without ever writing to it.
func OpenReadOnly(path string) (*DB, error) {
	return open(path, "&mode=ro")
}

func open(path, extra string) (*DB, error) {
	// SQLite URI filename: only these three characters would be misread.
	escaped := strings.NewReplacer("%", "%25", "?", "%3f", "#", "%23").Replace(filepath.ToSlash(path))
	dsn := "file:" + escaped + "?_pragma_key=" + url.QueryEscape(Key) +
		"&_busy_timeout=5000&_txlock=immediate" + extra
	conn, err := sql.Open("sqlite3", dsn)
	if err != nil {
		return nil, err
	}
	// One connection: SQLCipher keys are per connection, and we never need two.
	conn.SetMaxOpenConns(1)
	var n int
	if err := conn.QueryRow("SELECT count(*) FROM agentRegistry").Scan(&n); err != nil {
		conn.Close()
		return nil, fmt.Errorf("%s is not a Rekordbox library we can read: %w", path, err)
	}
	return &DB{sql: conn, Path: path}, nil
}

// Close checkpoints the WAL back into master.db and closes it.
func (d *DB) Close() error {
	_, _ = d.sql.Exec("PRAGMA wal_checkpoint(TRUNCATE)")
	return d.sql.Close()
}

// QuickCheck runs SQLite's structural check; "ok" is the only good answer.
func (d *DB) QuickCheck() error {
	var res string
	if err := d.sql.QueryRow("PRAGMA quick_check").Scan(&res); err != nil {
		return err
	}
	if res != "ok" {
		return fmt.Errorf("integrity check failed: %s", res)
	}
	return nil
}

// PathKey normalises a file path for identity comparisons: forward slashes,
// NFC (macOS hands out decomposed names), case-folded (both NTFS and APFS
// are case-insensitive by default).
func PathKey(p string) string {
	return strings.ToLower(norm.NFC.String(filepath.ToSlash(p)))
}

// FolderPath is the form Rekordbox stores in djmdContent.FolderPath: the
// absolute path with forward slashes, on every OS.
func FolderPath(p string) string {
	return filepath.ToSlash(p)
}

// KnownPaths returns the PathKey of every track in the collection.
func (d *DB) KnownPaths() (map[string]bool, error) {
	rows, err := d.sql.Query(
		"SELECT FolderPath FROM djmdContent WHERE rb_local_deleted = 0 AND FolderPath IS NOT NULL")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	known := map[string]bool{}
	for rows.Next() {
		var p string
		if err := rows.Scan(&p); err != nil {
			return nil, err
		}
		known[PathKey(p)] = true
	}
	return known, rows.Err()
}

// TrackCount is the number of tracks in the collection.
func (d *DB) TrackCount() (int, error) {
	var n int
	err := d.sql.QueryRow("SELECT count(*) FROM djmdContent WHERE rb_local_deleted = 0").Scan(&n)
	return n, err
}

// DominantFolder is the directory holding most of the collection — almost
// always the synced folder GetSetMix delivers into, so setup can propose it.
func (d *DB) DominantFolder() (string, error) {
	rows, err := d.sql.Query(
		"SELECT FolderPath FROM djmdContent WHERE rb_local_deleted = 0 AND FolderPath IS NOT NULL")
	if err != nil {
		return "", err
	}
	defer rows.Close()
	counts := map[string]int{}
	best, bestN := "", 0
	for rows.Next() {
		var p string
		if err := rows.Scan(&p); err != nil {
			return "", err
		}
		dir := p[:max(strings.LastIndex(p, "/"), 0)]
		counts[dir]++
		if counts[dir] > bestN {
			best, bestN = dir, counts[dir]
		}
	}
	if best == "" {
		return "", errors.New("the collection is empty")
	}
	return filepath.FromSlash(best), rows.Err()
}

func stamp(t time.Time) string {
	return t.UTC().Format(timeLayout)
}
