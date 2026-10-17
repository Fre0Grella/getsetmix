package scan

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestFolders(t *testing.T) {
	root := t.TempDir()
	old := time.Now().Add(-time.Hour)
	files := map[string]time.Time{
		"a.mp3":                        old,
		"sub/b.FLAC":                   old,
		"fresh.mp3":                    time.Now(), // still being written
		".a.mp3.~1f2e":                 old,        // Nextcloud temp
		"._a.mp3":                      old,        // macOS AppleDouble
		"c.mp3.part":                   old,
		"d (conflicted copy 2026).mp3": old,
		"notes.txt":                    old,
		".stversions/e.mp3":            old, // Syncthing's version folder
	}
	for name, mod := range files {
		path := filepath.Join(root, filepath.FromSlash(name))
		os.MkdirAll(filepath.Dir(path), 0o755)
		os.WriteFile(path, []byte("x"), 0o644)
		os.Chtimes(path, mod, mod)
	}
	os.WriteFile(filepath.Join(root, "empty.mp3"), nil, 0o644)

	res, err := Folders([]string{root}, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	var ready []string
	for _, f := range res.Ready {
		rel, _ := filepath.Rel(root, f.Path)
		ready = append(ready, filepath.ToSlash(rel))
	}
	if len(ready) != 2 || ready[0] != "a.mp3" || ready[1] != "sub/b.FLAC" {
		t.Errorf("ready = %v", ready)
	}
	if len(res.Settling) != 1 || filepath.Base(res.Settling[0].Path) != "fresh.mp3" {
		t.Errorf("settling = %v", res.Settling)
	}
}

func TestFoldersMissingRoot(t *testing.T) {
	if _, err := Folders([]string{filepath.Join(t.TempDir(), "gone")}, time.Now()); err == nil {
		t.Fatal("a missing watched folder must be an error, not an empty result")
	}
}
