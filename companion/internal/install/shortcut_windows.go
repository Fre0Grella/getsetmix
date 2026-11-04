package install

import (
	"errors"
	"fmt"
	"path/filepath"
	"runtime"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

// Shortcuts are written through the shell's own ShellLink COM object,
// in-process. Spawning PowerShell to drive WScript.Shell did the same job,
// but a hidden program launching `powershell -NonInteractive -Command` is
// one of the things antivirus heuristics read as a trojan (issue #16).

var procCoCreateInstance = windows.NewLazySystemDLL("ole32.dll").NewProc("CoCreateInstance")

var (
	clsidShellLink  = windows.GUID{Data1: 0x00021401, Data4: [8]byte{0xC0, 0, 0, 0, 0, 0, 0, 0x46}}
	iidIShellLinkW  = windows.GUID{Data1: 0x000214F9, Data4: [8]byte{0xC0, 0, 0, 0, 0, 0, 0, 0x46}}
	iidIPersistFile = windows.GUID{Data1: 0x0000010B, Data4: [8]byte{0xC0, 0, 0, 0, 0, 0, 0, 0x46}}
)

// vtable slots, in declaration order (IUnknown takes 0-2).
const (
	slotQueryInterface  = 0
	slotRelease         = 2
	slotSetDescription  = 7  // IShellLinkW
	slotSetWorkingDir   = 9  // IShellLinkW
	slotSetArguments    = 11 // IShellLinkW
	slotSetShowCmd      = 15 // IShellLinkW
	slotSetIconLocation = 17 // IShellLinkW
	slotSetPath         = 20 // IShellLinkW
	slotSave            = 6  // IPersistFile
)

const (
	swShowNormal      = 1
	swShowMinNoActive = 7
	rpcEChangedMode   = 0x80010106 // COM already set up differently on this thread
)

// comCall invokes vtable slot of the COM object obj.
func comCall(obj unsafe.Pointer, slot int, args ...uintptr) error {
	vtbl := *(*unsafe.Pointer)(obj)
	fn := *(*uintptr)(unsafe.Add(vtbl, slot*int(unsafe.Sizeof(uintptr(0)))))
	hr, _, _ := syscall.SyscallN(fn, append([]uintptr{uintptr(obj)}, args...)...)
	if int32(hr) < 0 {
		return syscall.Errno(hr)
	}
	return nil
}

// comString calls a setter that takes one UTF-16 string.
func comString(obj unsafe.Pointer, slot int, s string) error {
	p, err := windows.UTF16PtrFromString(s)
	if err != nil {
		return err
	}
	err = comCall(obj, slot, uintptr(unsafe.Pointer(p)))
	runtime.KeepAlive(p)
	return err
}

// makeShortcut writes the .lnk file lnk that runs target with args.
func makeShortcut(lnk, target, args, icon, description string, minimized bool) error {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	switch err := windows.CoInitializeEx(0, windows.COINIT_APARTMENTTHREADED); {
	case err == nil, errors.Is(err, syscall.Errno(1)): // S_OK, S_FALSE
		defer windows.CoUninitialize()
	case errors.Is(err, syscall.Errno(rpcEChangedMode)):
		// Usable as it is; it isn't ours to uninitialise.
	default:
		return fmt.Errorf("CoInitializeEx: %w", err)
	}

	var link unsafe.Pointer
	hr, _, _ := procCoCreateInstance.Call(
		uintptr(unsafe.Pointer(&clsidShellLink)), 0, windows.CLSCTX_INPROC_SERVER,
		uintptr(unsafe.Pointer(&iidIShellLinkW)), uintptr(unsafe.Pointer(&link)))
	if int32(hr) < 0 {
		return fmt.Errorf("creating ShellLink: %w", syscall.Errno(hr))
	}
	defer comCall(link, slotRelease)

	show := uintptr(swShowNormal)
	if minimized {
		show = swShowMinNoActive
	}
	steps := []struct {
		what string
		err  func() error
	}{
		{"target", func() error { return comString(link, slotSetPath, target) }},
		{"arguments", func() error { return comString(link, slotSetArguments, args) }},
		{"working folder", func() error { return comString(link, slotSetWorkingDir, filepath.Dir(target)) }},
		{"description", func() error { return comString(link, slotSetDescription, description) }},
		{"window style", func() error { return comCall(link, slotSetShowCmd, show) }},
		{"icon", func() error {
			p, err := windows.UTF16PtrFromString(icon)
			if err != nil {
				return err
			}
			err = comCall(link, slotSetIconLocation, uintptr(unsafe.Pointer(p)), 0)
			runtime.KeepAlive(p)
			return err
		}},
	}
	for _, s := range steps {
		if err := s.err(); err != nil {
			return fmt.Errorf("setting the shortcut's %s: %w", s.what, err)
		}
	}

	var file unsafe.Pointer
	if err := comCall(link, slotQueryInterface,
		uintptr(unsafe.Pointer(&iidIPersistFile)), uintptr(unsafe.Pointer(&file))); err != nil {
		return fmt.Errorf("IPersistFile: %w", err)
	}
	defer comCall(file, slotRelease)
	p, err := windows.UTF16PtrFromString(lnk)
	if err != nil {
		return err
	}
	err = comCall(file, slotSave, uintptr(unsafe.Pointer(p)), 1)
	runtime.KeepAlive(p)
	if err != nil {
		return fmt.Errorf("saving: %w", err)
	}
	return nil
}
