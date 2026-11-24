// Package recycle sends a file to the system's recycle bin: the Windows
// Recycle Bin or the macOS Trash. It never deletes a file for good: where no
// bin is available, Move fails and the file stays where it is
// (docs/design/library.md, 4.6, decision 15).
package recycle

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
)

// ErrUnsupported means this system has no recycle bin GetSetMix can use.
var ErrUnsupported = errors.New("no recycle bin on this system: the file was left in place")

// Move sends the regular file at path to the recycle bin.
func Move(path string) error {
	abs, err := filepath.Abs(path)
	if err != nil {
		return err
	}
	info, err := os.Lstat(abs)
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("%s is not a file", abs)
	}
	if err := move(abs); err != nil {
		return err
	}
	if _, err := os.Lstat(abs); err == nil {
		return fmt.Errorf("%s is still there after moving it to the recycle bin", abs)
	}
	return nil
}
