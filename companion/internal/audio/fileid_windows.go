package audio

import (
	"os"

	"golang.org/x/sys/windows"
)

// fileID is the NTFS file ID — exactly what Rekordbox stores as rb_file_id
// on Windows (checked against `fsutil file queryfileid`).
func fileID(f *os.File) (uint64, error) {
	var info windows.ByHandleFileInformation
	if err := windows.GetFileInformationByHandle(windows.Handle(f.Fd()), &info); err != nil {
		return 0, err
	}
	return uint64(info.FileIndexHigh)<<32 | uint64(info.FileIndexLow), nil
}
