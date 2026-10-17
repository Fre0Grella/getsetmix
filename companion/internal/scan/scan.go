// Package scan finds audio files in the watched folders that are ready to
// import: complete (not still being written by a sync client) and not
// handled before.
package scan

import (
	"io/fs"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/audio"
	"github.com/Fre0Grella/getsetmix/companion/internal/library"
)

// SettleTime is how long a file must go unmodified before it counts as
// complete. Sync clients download into temp names and rename at the end,
// but some write in place; this covers both.
const SettleTime = 10 * time.Second

// File is an audio file found in a watched folder.
type File struct {
	Path    string
	Key     string // library.PathKey(Path)
	ModTime time.Time
	Size    int64
}

// Result of a scan.
type Result struct {
	Ready    []File // complete files, sorted by path
	Settling []File // seen, but modified less than SettleTime ago
}

// Folders walks every folder recursively.
func Folders(folders []string, now time.Time) (Result, error) {
	var res Result
	seen := map[string]bool{}
	for _, root := range folders {
		err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
			if err != nil {
				if path == root {
					return err
				}
				return nil // unreadable subfolder: skip it, keep going
			}
			name := d.Name()
			if d.IsDir() {
				if path != root && Ignored(name) {
					return filepath.SkipDir
				}
				return nil
			}
			if Ignored(name) || !audio.Supported(name) {
				return nil
			}
			info, err := d.Info()
			if err != nil || info.Size() == 0 {
				return nil
			}
			key := library.PathKey(path)
			if seen[key] {
				return nil
			}
			seen[key] = true
			f := File{Path: path, Key: key, ModTime: info.ModTime(), Size: info.Size()}
			if now.Sub(f.ModTime) < SettleTime {
				res.Settling = append(res.Settling, f)
			} else {
				res.Ready = append(res.Ready, f)
			}
			return nil
		})
		if err != nil {
			return res, err
		}
	}
	sort.Slice(res.Ready, func(i, j int) bool { return res.Ready[i].Path < res.Ready[j].Path })
	return res, nil
}

// Ignored reports names no sync client or OS means as a finished track:
// hidden/temp files (Nextcloud's ".name.~1a2b", macOS "._name"), partial
// downloads, and conflict copies.
func Ignored(name string) bool {
	lower := strings.ToLower(name)
	if strings.HasPrefix(name, ".") || strings.HasPrefix(name, "~") {
		return true
	}
	for _, suffix := range []string{".part", ".partial", ".tmp", ".crdownload", ".download", "~"} {
		if strings.HasSuffix(lower, suffix) {
			return true
		}
	}
	return strings.Contains(lower, "(conflicted copy") || strings.Contains(lower, ".sync-conflict-")
}
