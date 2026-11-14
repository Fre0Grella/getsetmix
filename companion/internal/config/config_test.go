package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/scan"
)

func TestStateReadsBothFormsOfAValue(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "state.json"), []byte(`{
  "baseline": "2026-10-01T18:00:00Z",
  "seen": {
    "old": "2026-10-02T18:00:00Z",
    "new": {"at": "2026-10-03T18:00:00Z", "size": 1234, "mtime": 1700000000000000000}
  }
}`), 0o644)
	s, err := LoadState(dir)
	if err != nil {
		t.Fatal(err)
	}
	if got := s.Seen["old"]; !got.At.Equal(time.Date(2026, 10, 2, 18, 0, 0, 0, time.UTC)) || got.Widened() {
		t.Errorf("old value: %+v", got)
	}
	if got := s.Seen["new"]; got.Size != 1234 || got.MTime != 1_700_000_000_000_000_000 || !got.Widened() {
		t.Errorf("new value: %+v", got)
	}

	// Widen fills what is missing and leaves the rest as it was.
	mtime := time.Unix(1_750_000_000, 5)
	if !s.Widen([]scan.File{{Key: "old", Size: 99, ModTime: mtime}, {Key: "new", Size: 1, ModTime: mtime},
		{Key: "unknown", Size: 7, ModTime: mtime}}) {
		t.Fatal("nothing widened")
	}
	if got := s.Seen["old"]; got.Size != 99 || got.MTime != mtime.UnixNano() ||
		!got.At.Equal(time.Date(2026, 10, 2, 18, 0, 0, 0, time.UTC)) {
		t.Errorf("widened: %+v", got)
	}
	if s.Seen["new"].Size != 1234 {
		t.Error("a widened value was changed")
	}
	if _, ok := s.Seen["unknown"]; ok {
		t.Error("Widen marked a file that was never handled")
	}
	if s.Widen([]scan.File{{Key: "old", Size: 5, ModTime: mtime}}) {
		t.Error("widened twice")
	}

	if err := s.Save(dir); err != nil {
		t.Fatal(err)
	}
	var onDisk struct {
		Seen map[string]map[string]any `json:"seen"`
	}
	data, _ := os.ReadFile(filepath.Join(dir, "state.json"))
	if err := json.Unmarshal(data, &onDisk); err != nil {
		t.Fatalf("%v: %s", err, data)
	}
	if v := onDisk.Seen["old"]; v["at"] != "2026-10-02T18:00:00Z" || v["size"] != 99.0 || v["mtime"] == nil {
		t.Errorf("saved value: %v", v)
	}
}
