package library

import (
	"database/sql"
	"errors"
	"time"
)

// RemovedPlaylist is the root playlist that lists the tracks the server
// removed (docs/design/library.md, 4.6). Nothing is ever removed from the
// collection: removing a track would also lose its cues, grid and playlist
// entries, and that decision is the DJ's.
const RemovedPlaylist = "GetSetMix: removed on server"

// RemovedResult says what MarkRemoved did.
type RemovedResult struct {
	Added    []string // paths added to the playlist
	Already  []string // paths that were in it already: never added twice
	Dropped  []string // paths taken out of it
	NotFound []string // paths no collection row has: the DJ removed the track
	// Playlist is the removed playlist when it was written, for the
	// masterPlaylists6.xml mirror; its ID is empty when it was not.
	Playlist Playlist
}

// MarkRemoved lists the collection rows of the files in add in the removed
// playlist, created when missing, and takes the rows of the files in drop
// out of it, in one transaction. A row is never listed twice. The rows
// themselves, their cues and their other playlist entries are not touched.
func (d *DB) MarkRemoved(add, drop []string, now time.Time) (RemovedResult, error) {
	var res RemovedResult
	tx, err := d.sql.Begin()
	if err != nil {
		return res, err
	}
	defer tx.Rollback() //nolint:errcheck // no-op after Commit

	w := &writer{tx: tx, now: stamp(now), date: now.Local().Format("2006-01-02"), cache: map[string]string{}}
	if err := w.loadContext(); err != nil {
		return res, err
	}
	ids, err := contentIDs(tx)
	if err != nil {
		return res, err
	}
	plID, err := findPlaylist(tx, RemovedPlaylist)
	if err != nil {
		return res, err
	}
	created := false
	changed := false

	var toAdd []string
	listed := map[string]bool{}
	for _, p := range add {
		cid, ok := ids[PathKey(p)]
		if !ok {
			res.NotFound = append(res.NotFound, p)
			continue
		}
		in := listed[cid]
		if !in && plID != "" {
			if in, err = inPlaylist(tx, plID, cid); err != nil {
				return res, err
			}
		}
		if in {
			res.Already = append(res.Already, p)
			continue
		}
		listed[cid] = true
		toAdd = append(toAdd, cid)
		res.Added = append(res.Added, p)
	}
	if len(toAdd) > 0 {
		pl, err := w.ensurePlaylist(RemovedPlaylist)
		if err != nil {
			return res, err
		}
		plID, created = pl.ID, pl.Created
		if err := w.appendToPlaylist(plID, toAdd); err != nil {
			return res, err
		}
		changed = true
	}

	if plID != "" {
		dropped := false
		for _, p := range drop {
			cid, ok := ids[PathKey(p)]
			if !ok {
				continue
			}
			r, err := tx.Exec(`DELETE FROM djmdSongPlaylist WHERE PlaylistID = ? AND ContentID = ?`, plID, cid)
			if err != nil {
				return res, err
			}
			if n, _ := r.RowsAffected(); n > 0 {
				res.Dropped = append(res.Dropped, p)
				dropped = true
			}
		}
		if dropped {
			if err := w.renumber(plID); err != nil {
				return res, err
			}
			changed = true
		}
	}

	if !changed {
		return res, tx.Commit()
	}
	if _, err := tx.Exec("UPDATE agentRegistry SET int_1 = ? WHERE registry_id = 'localUpdateCount'", w.usn); err != nil {
		return res, err
	}
	if err := tx.Commit(); err != nil {
		return res, err
	}
	res.Playlist = Playlist{ID: plID, Created: created, UpdatedAt: now}
	return res, nil
}

// contentIDs maps the PathKey of every track in the collection to its ID.
func contentIDs(tx *sql.Tx) (map[string]string, error) {
	rows, err := tx.Query(`SELECT ID, FolderPath FROM djmdContent
		WHERE rb_local_deleted = 0 AND FolderPath IS NOT NULL`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	ids := map[string]string{}
	for rows.Next() {
		var id, p string
		if err := rows.Scan(&id, &p); err != nil {
			return nil, err
		}
		ids[PathKey(p)] = id
	}
	return ids, rows.Err()
}

// findPlaylist is the ID of the root playlist called name, or "" when there
// is none.
func findPlaylist(tx *sql.Tx, name string) (string, error) {
	var id string
	err := tx.QueryRow(`SELECT ID FROM djmdPlaylist
		WHERE Name = ? AND ParentID = 'root' AND Attribute = 0 AND rb_local_deleted = 0
		ORDER BY Seq LIMIT 1`, name).Scan(&id)
	if errors.Is(err, sql.ErrNoRows) {
		return "", nil
	}
	return id, err
}

func inPlaylist(tx *sql.Tx, playlistID, contentID string) (bool, error) {
	var n int
	err := tx.QueryRow(`SELECT count(*) FROM djmdSongPlaylist
		WHERE PlaylistID = ? AND ContentID = ? AND rb_local_deleted = 0`, playlistID, contentID).Scan(&n)
	return n > 0, err
}

// renumber closes the gaps a removal leaves in a playlist's TrackNo, as
// Rekordbox does: every entry that moves gets the next change number.
func (w *writer) renumber(playlistID string) error {
	rows, err := w.tx.Query(`SELECT ID, TrackNo FROM djmdSongPlaylist
		WHERE PlaylistID = ? AND rb_local_deleted = 0 ORDER BY TrackNo, ID`, playlistID)
	if err != nil {
		return err
	}
	type entry struct {
		id string
		no sql.NullInt64
	}
	var entries []entry
	for rows.Next() {
		var e entry
		if err := rows.Scan(&e.id, &e.no); err != nil {
			rows.Close()
			return err
		}
		entries = append(entries, e)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return err
	}
	for i, e := range entries {
		if e.no.Valid && e.no.Int64 == int64(i+1) {
			continue
		}
		if _, err := w.tx.Exec(`UPDATE djmdSongPlaylist SET TrackNo = ?, rb_local_usn = ?, updated_at = ?
			WHERE ID = ?`, i+1, w.nextUSN(), w.now, e.id); err != nil {
			return err
		}
	}
	_, err = w.tx.Exec("UPDATE djmdPlaylist SET updated_at = ?, rb_local_usn = ? WHERE ID = ?",
		w.now, w.nextUSN(), playlistID)
	return err
}
