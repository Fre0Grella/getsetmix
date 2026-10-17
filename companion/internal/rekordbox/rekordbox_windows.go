package rekordbox

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"unsafe"

	"golang.org/x/sys/windows"
)

func pioneerAppDir() string {
	return filepath.Join(os.Getenv("APPDATA"), "Pioneer")
}

func findExe() string {
	var found []string
	for _, base := range []string{os.Getenv("ProgramW6432"), os.Getenv("ProgramFiles")} {
		if base == "" {
			continue
		}
		m, _ := filepath.Glob(filepath.Join(base, "rekordbox", "rekordbox *", "rekordbox.exe"))
		found = append(found, m...)
	}
	return newest(found, folderVersion)
}

// Running returns the PIDs of rekordbox.exe.
func Running() ([]uint32, error) {
	snap, err := windows.CreateToolhelp32Snapshot(windows.TH32CS_SNAPPROCESS, 0)
	if err != nil {
		return nil, err
	}
	defer windows.CloseHandle(snap)
	var pe windows.ProcessEntry32
	pe.Size = uint32(unsafe.Sizeof(pe))
	var pids []uint32
	for err = windows.Process32First(snap, &pe); err == nil; err = windows.Process32Next(snap, &pe) {
		if strings.EqualFold(windows.UTF16ToString(pe.ExeFile[:]), "rekordbox.exe") {
			pids = append(pids, pe.ProcessID)
		}
	}
	return pids, nil
}

// waitExit sleeps on the process handles until all of them exit.
func waitExit(ctx context.Context, pids []uint32) error {
	var handles []windows.Handle
	for _, pid := range pids {
		if h, err := windows.OpenProcess(windows.SYNCHRONIZE, false, pid); err == nil {
			handles = append(handles, h)
		}
	}
	defer func() {
		for _, h := range handles {
			windows.CloseHandle(h)
		}
	}()
	for len(handles) > 0 {
		// Wake once a minute only to notice a cancelled context.
		ev, err := windows.WaitForMultipleObjects(handles, true, 60_000)
		if err != nil {
			return err
		}
		if ev != uint32(windows.WAIT_TIMEOUT) {
			return nil
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
	}
	return nil
}

// Launch starts Rekordbox detached from this process, which may then exit.
func Launch(exe string) error {
	cmd := exec.Command(exe)
	cmd.Dir = filepath.Dir(exe)
	cmd.SysProcAttr = &windows.SysProcAttr{
		CreationFlags: windows.DETACHED_PROCESS | windows.CREATE_NEW_PROCESS_GROUP,
	}
	return cmd.Start()
}
