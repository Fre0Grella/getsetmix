package recycle

import (
	"errors"
	"fmt"
	"path/filepath"
	"unsafe"

	"golang.org/x/sys/windows"
)

var procSHFileOperation = windows.NewLazySystemDLL("shell32.dll").NewProc("SHFileOperationW")

const (
	foDelete           = 0x0003
	fofSilent          = 0x0004 // no progress window
	fofNoConfirmation  = 0x0010 // no "move to the Recycle Bin?" question
	fofAllowUndo       = 0x0040 // to the Recycle Bin
	fofNoErrorUI       = 0x0400
	fofWantNukeWarning = 0x4000 // ask, rather than delete for good, when recycling is impossible
)

// shFileOpStruct is SHFILEOPSTRUCTW with the natural alignment of 64-bit
// Windows, the only one the companion ships for.
type shFileOpStruct struct {
	hwnd                  uintptr
	wFunc                 uint32
	pFrom                 *uint16
	pTo                   *uint16
	fFlags                uint16
	fAnyOperationsAborted int32
	hNameMappings         uintptr
	lpszProgressTitle     *uint16
}

func move(abs string) error {
	// Only local fixed drives have a Recycle Bin. On a network share or a
	// USB stick Windows deletes for good, so the file is left alone there.
	root := filepath.VolumeName(abs) + `\`
	rootPtr, err := windows.UTF16PtrFromString(root)
	if err != nil {
		return err
	}
	if t := windows.GetDriveType(rootPtr); t != windows.DRIVE_FIXED {
		return fmt.Errorf("%s has no Recycle Bin (drive type %d): the file was left in place", root, t)
	}
	from, err := windows.UTF16FromString(abs)
	if err != nil {
		return err
	}
	from = append(from, 0) // a list of names, ended by an empty one
	op := shFileOpStruct{
		wFunc:  foDelete,
		pFrom:  &from[0],
		fFlags: fofAllowUndo | fofNoConfirmation | fofSilent | fofNoErrorUI | fofWantNukeWarning,
	}
	r, _, _ := procSHFileOperation.Call(uintptr(unsafe.Pointer(&op)))
	if r != 0 {
		return fmt.Errorf("moving to the Recycle Bin failed (code %#x)", r)
	}
	if op.fAnyOperationsAborted != 0 {
		return errors.New("moving to the Recycle Bin was cancelled")
	}
	return nil
}
