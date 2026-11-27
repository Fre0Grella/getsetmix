package library

import (
	"database/sql"

	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

// querier is what a lookup needs, from a *sql.DB or inside a *sql.Tx.
type querier interface {
	Query(query string, args ...any) (*sql.Rows, error)
	QueryRow(query string, args ...any) *sql.Row
}

// localDevice is the djmdDevice ID of this computer: djmdProperty names it;
// failing that, the device most tracks belong to (there can be others, e.g. a
// USB stick's). It is "" when neither tells.
func localDevice(q querier) string {
	var id string
	_ = q.QueryRow("SELECT DeviceID FROM djmdProperty LIMIT 1").Scan(&id)
	if id == "" {
		_ = q.QueryRow(`SELECT DeviceID FROM djmdContent WHERE DeviceID IS NOT NULL
			GROUP BY DeviceID ORDER BY count(*) DESC LIMIT 1`).Scan(&id)
	}
	return id
}

// rowsByPath maps the PathKey of every file in the collection to the ID of
// the live row that speaks for it, the same row for every write: an update,
// the removed playlist and a restore from it (docs/design/library.md, 4.6.1).
//
// When Rekordbox holds several live rows for one file, the oldest row of
// device (this computer) wins: a duplicate is usually a leftover, and the
// oldest row is the one Rekordbox has had longest, most likely the one with
// the cues. When device has no row for the file, the oldest row of any
// device wins, so a file is never left without one.
func rowsByPath(q querier, device string) (map[string]string, error) {
	rows, err := q.Query(`SELECT ID, FolderPath, coalesce(DeviceID, '') FROM djmdContent
		WHERE rb_local_deleted = 0 AND FolderPath IS NOT NULL ORDER BY created_at, ID`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	ids := map[string]string{}
	ours := map[string]bool{} // the winner so far is device's row
	for rows.Next() {
		var id, p, dev string
		if err := rows.Scan(&id, &p, &dev); err != nil {
			return nil, err
		}
		key := track.PathKey(p)
		_, seen := ids[key]
		mine := device != "" && dev == device
		if !seen || (mine && !ours[key]) {
			ids[key], ours[key] = id, mine
		}
	}
	return ids, rows.Err()
}

// knownPaths is the PathKey of every file in the collection, whichever device
// its rows belong to: a file is already there if any live row holds it.
func knownPaths(q querier) (map[string]bool, error) {
	ids, err := rowsByPath(q, "")
	if err != nil {
		return nil, err
	}
	known := make(map[string]bool, len(ids))
	for key := range ids {
		known[key] = true
	}
	return known, nil
}
