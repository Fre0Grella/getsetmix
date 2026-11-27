package library_test

import (
	"database/sql"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/Fre0Grella/getsetmix/companion/internal/library"
	"github.com/Fre0Grella/getsetmix/companion/internal/library/librarytest"
	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

// duplicate adds a second live row for the file of row id, as Rekordbox can
// hold: a copy with another ID, creation time and device.
func duplicate(t *testing.T, dir, id, newID, created, device string) {
	t.Helper()
	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	for _, q := range []struct {
		sql  string
		args []any
	}{
		{`CREATE TEMP TABLE dup AS SELECT * FROM djmdContent WHERE ID = ?`, []any{id}},
		{`UPDATE dup SET ID = ?, created_at = ?, DeviceID = ?`, []any{newID, created, device}},
		{`INSERT INTO djmdContent SELECT * FROM dup`, nil},
	} {
		if _, err := raw.Exec(q.sql, q.args...); err != nil {
			t.Fatal(err)
		}
	}
}

// edit writes a new comment for path through Update.
func edit(t *testing.T, dir, path string) {
	t.Helper()
	db, err := library.Open(filepath.Join(dir, "master.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	res, err := db.Update([]library.Change{{Path: path, Tags: track.Tags{Comment: "edited"},
		Fields: []string{track.FieldComment}, FileSize: 1}}, now)
	if err != nil || len(res.Updated) != 1 {
		t.Fatalf("update: %+v, %v", res, err)
	}
}

// edited names the rows, of those given, that hold the comment edit wrote.
func edited(t *testing.T, dir string, ids ...string) []string {
	t.Helper()
	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	var out []string
	for _, id := range ids {
		var c sql.NullString
		if err := raw.QueryRow("SELECT Commnt FROM djmdContent WHERE ID = ?", id).Scan(&c); err != nil {
			t.Fatal(err)
		}
		if c.String == "edited" {
			out = append(out, id)
		}
	}
	return out
}

func listed(t *testing.T, dir string) []string {
	t.Helper()
	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	return removedList(t, raw)
}

func idOf(t *testing.T, dir, path string) string {
	t.Helper()
	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	defer raw.Close()
	return contentID(t, raw, path)
}

// When Rekordbox holds two live rows of this computer for one file, every
// write picks the same one, the oldest: an update changes it alone, the
// removed playlist lists it, and a restore takes that row out again. The
// file still counts once as known.
func TestADuplicatedPathIsAlwaysItsOldestRow(t *testing.T) {
	t.Parallel()
	dir, paths := removedSetup(t)
	oldest := idOf(t, dir, paths[1])
	db, err := library.Open(filepath.Join(dir, "master.db"))
	if err != nil {
		t.Fatal(err)
	}
	before, err := db.KnownPaths()
	db.Close()
	if err != nil {
		t.Fatal(err)
	}
	duplicate(t, dir, oldest, "dup1", "2999-01-01 00:00:00.000 +00:00", librarytest.DeviceID)

	markRemoved(t, dir, []string{paths[1]}, nil, now)
	if got := listed(t, dir); !reflect.DeepEqual(got, []string{oldest}) {
		t.Fatalf("removed playlist %v, want the oldest row %s", got, oldest)
	}
	edit(t, dir, paths[1])
	if got := edited(t, dir, oldest, "dup1"); !reflect.DeepEqual(got, []string{oldest}) {
		t.Fatalf("update changed %v, want the oldest row only", got)
	}
	markRemoved(t, dir, nil, []string{paths[1]}, now)
	if got := listed(t, dir); len(got) != 0 {
		t.Fatalf("after the restore the playlist holds %v", got)
	}

	db, err = library.Open(filepath.Join(dir, "master.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if after, err := db.KnownPaths(); err != nil || !reflect.DeepEqual(after, before) {
		t.Fatalf("known paths %v, want %v (%v)", after, before, err)
	}
}

// A row of another device is passed over when this computer has its own row
// for the file, even if the other one is older: the duplicate is usually a
// leftover Rekordbox does not use.
func TestThisComputersRowWinsOverAnOlderRowOfAnotherDevice(t *testing.T) {
	t.Parallel()
	dir, paths := removedSetup(t)
	ours := idOf(t, dir, paths[1])
	duplicate(t, dir, ours, "usb1", "1999-01-01 00:00:00.000 +00:00", librarytest.USBDeviceID)

	markRemoved(t, dir, []string{paths[1]}, nil, now)
	if got := listed(t, dir); !reflect.DeepEqual(got, []string{ours}) {
		t.Fatalf("removed playlist %v, want this computer's row %s", got, ours)
	}
	edit(t, dir, paths[1])
	if got := edited(t, dir, ours, "usb1"); !reflect.DeepEqual(got, []string{ours}) {
		t.Fatalf("update changed %v, want this computer's row only", got)
	}
}

// When only another device holds a row for the file, that row is still the
// one written, so no file is left without updates.
func TestAnotherDevicesRowIsUsedWhenThisComputerHasNone(t *testing.T) {
	t.Parallel()
	dir, paths := removedSetup(t)
	id := idOf(t, dir, paths[1])
	raw := librarytest.Open(t, filepath.Join(dir, "master.db"))
	if _, err := raw.Exec("UPDATE djmdContent SET DeviceID = ? WHERE ID = ?", librarytest.USBDeviceID, id); err != nil {
		t.Fatal(err)
	}
	raw.Close()

	markRemoved(t, dir, []string{paths[1]}, nil, now)
	if got := listed(t, dir); !reflect.DeepEqual(got, []string{id}) {
		t.Fatalf("removed playlist %v, want %s", got, id)
	}
	edit(t, dir, paths[1])
	if got := edited(t, dir, id); !reflect.DeepEqual(got, []string{id}) {
		t.Fatal("the other device's row was not updated")
	}
}
