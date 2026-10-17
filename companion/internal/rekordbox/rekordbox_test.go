package rekordbox

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestAgentDBDir(t *testing.T) {
	pioneer := t.TempDir()
	storage := filepath.Join(pioneer, "rekordboxAgent", "storage")
	os.MkdirAll(storage, 0o755)
	db := filepath.Join("D:", "DJ", "rekordbox", "master.db")
	opts, _ := json.Marshal(map[string]any{
		"options":  [][]string{{"languages", "en"}, {"db-path", db}},
		"defaults": map[string]any{},
	})
	os.WriteFile(filepath.Join(storage, "options.json"), opts, 0o644)
	if got := agentDBDir(pioneer); got != filepath.Dir(db) {
		t.Fatalf("got %q", got)
	}
	if got := agentDBDir(t.TempDir()); got != "" {
		t.Fatalf("no options.json should mean no override, got %q", got)
	}
}

func TestNewest(t *testing.T) {
	got := newest([]string{
		"/p/rekordbox 6.8.5/rekordbox.exe",
		"/p/rekordbox 7.2.19/rekordbox.exe",
		"/p/rekordbox 7.10.0/rekordbox.exe",
	}, folderVersion)
	if got != "/p/rekordbox 7.10.0/rekordbox.exe" {
		t.Fatalf("got %q", got)
	}
}
