package library

import (
	"database/sql"
	"fmt"
	"path/filepath"
	"strconv"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

// Change is a track already in the collection whose file was replaced by a
// newer copy from the server.
type Change struct {
	Path     string     // absolute path on this machine, as in FolderPath
	Tags     track.Tags // the file's tags now
	Fields   []string   // the fields to write: those that changed on the server
	FileSize int64      // the file's new size
	FileID   uint64     // the file's new filesystem id; 0 when it could not be read
}

// UpdateResult says what Update did.
type UpdateResult struct {
	Updated []string // paths whose row was updated
	Missing []string // paths with no row: removed from Rekordbox, left out
}

// Update brings the rows of changed files in line with them, in one
// transaction (docs/design/library.md, 4.6). Per row it writes only the
// fields named in the change (title, the artist, album and genre ids, the
// release year, the comment), the file's new size and filesystem id, and the
// change counters. Nothing else in the row is touched: cues, the beat grid,
// ratings, play counts and playlist entries hang off the row's ID, which does
// not change. A path with no row is not imported again.
func (d *DB) Update(changes []Change, now time.Time) (UpdateResult, error) {
	var res UpdateResult
	tx, err := d.sql.Begin()
	if err != nil {
		return res, err
	}
	defer tx.Rollback() //nolint:errcheck // no-op after Commit

	w := &writer{tx: tx, now: stamp(now), cache: map[string]string{}}
	if err := tx.QueryRow(
		"SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'").Scan(&w.usn); err != nil {
		return res, fmt.Errorf("reading localUpdateCount: %w", err)
	}

	ids, err := rowsByPath(tx, localDevice(tx))
	if err != nil {
		return res, err
	}

	for _, c := range changes {
		id, ok := ids[track.PathKey(c.Path)]
		if !ok {
			res.Missing = append(res.Missing, c.Path)
			continue
		}
		if err := w.updateContent(id, c); err != nil {
			return res, fmt.Errorf("%s: %w", filepath.Base(c.Path), err)
		}
		res.Updated = append(res.Updated, c.Path)
	}
	if len(res.Updated) > 0 {
		if _, err := tx.Exec(
			"UPDATE agentRegistry SET int_1 = ? WHERE registry_id = 'localUpdateCount'", w.usn); err != nil {
			return res, err
		}
	}
	return res, tx.Commit()
}

func (w *writer) updateContent(id string, c Change) error {
	sets := []string{}
	var args []any
	set := func(col string, v any) {
		sets = append(sets, col+" = ?")
		args = append(args, v)
	}
	for _, f := range c.Fields {
		switch f {
		case track.FieldTitle:
			title := c.Tags.Title
			if title == "" {
				title = trimExt(filepath.Base(c.Path)) // as an import does
			}
			set("Title", title)
		case track.FieldArtist, track.FieldAlbum, track.FieldGenre:
			table, col, name := "djmdArtist", "ArtistID", c.Tags.Artist
			if f == track.FieldAlbum {
				table, col, name = "djmdAlbum", "AlbumID", c.Tags.Album
			} else if f == track.FieldGenre {
				table, col, name = "djmdGenre", "GenreID", c.Tags.Genre
			}
			ref, err := w.ensureNamed(table, name)
			if err != nil {
				return err
			}
			set(col, ref)
		case track.FieldYear:
			set("ReleaseYear", nullInt(c.Tags.Year))
		case track.FieldComment:
			set("Commnt", nullStr(c.Tags.Comment))
		default:
			return fmt.Errorf("unknown field %q", f)
		}
	}
	set("FileSize", c.FileSize)
	if c.FileID != 0 {
		set("rb_file_id", sql.NullString{String: strconv.FormatUint(c.FileID, 10), Valid: true})
	}
	set("updated_at", w.now)
	set("rb_local_usn", w.nextUSN())
	q := "UPDATE djmdContent SET "
	for i, s := range sets {
		if i > 0 {
			q += ", "
		}
		q += s
	}
	_, err := w.tx.Exec(q+" WHERE ID = ?", append(args, id)...)
	return err
}
