//go:build !windows

package audio

import (
	"os"
	"syscall"
)

// fileID is the inode number, the macOS counterpart of the NTFS file ID.
func fileID(f *os.File) (uint64, error) {
	info, err := f.Stat()
	if err != nil {
		return 0, err
	}
	if st, ok := info.Sys().(*syscall.Stat_t); ok {
		return uint64(st.Ino), nil
	}
	return 0, nil
}
