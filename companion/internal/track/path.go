package track

import (
	"fmt"
	"os"
	"path"
	"path/filepath"
	"strings"

	"golang.org/x/text/unicode/norm"
)

// PathKey normalises a file path for identity comparisons: forward slashes,
// NFC (macOS hands out decomposed names), case-folded (both NTFS and APFS
// are case-insensitive by default).
func PathKey(p string) string {
	return strings.ToLower(norm.NFC.String(filepath.ToSlash(p)))
}

// Local maps a server path onto this computer, refusing anything that would
// land outside the folder.
func Local(folder, serverPath string) (string, error) {
	clean := path.Clean("/" + serverPath)[1:]
	if clean == "" || clean != serverPath || strings.Contains(serverPath, "\\") {
		return "", fmt.Errorf("unsafe path %q", serverPath)
	}
	return filepath.Join(folder, filepath.FromSlash(clean)), nil
}

// HasSize reports whether file is a regular file of size bytes: a track
// already in place, as far as a listing can tell.
func HasSize(file string, size int64) bool {
	info, err := os.Stat(file)
	return err == nil && info.Mode().IsRegular() && info.Size() == size
}
