package rekordbox

import (
	"bytes"
	"context"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"golang.org/x/sys/unix"
)

func pioneerAppDir() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, "Library", "Pioneer")
}

func findExe() string {
	found, _ := filepath.Glob("/Applications/rekordbox */rekordbox.app")
	return newest(found, func(app string) string { return folderVersion(filepath.Join(app, "x")) })
}

// Running returns the PIDs of the rekordbox process.
func Running() ([]uint32, error) {
	procs, err := unix.SysctlKinfoProcSlice("kern.proc.all")
	if err != nil {
		return nil, err
	}
	var pids []uint32
	for _, p := range procs {
		name := p.Proc.P_comm[:]
		if i := bytes.IndexByte(name, 0); i >= 0 {
			name = name[:i]
		}
		if string(name) == "rekordbox" {
			pids = append(pids, uint32(p.Proc.P_pid))
		}
	}
	return pids, nil
}

// waitExit sleeps in kqueue until every pid has exited.
func waitExit(ctx context.Context, pids []uint32) error {
	kq, err := unix.Kqueue()
	if err != nil {
		return err
	}
	defer unix.Close(kq)
	changes := make([]unix.Kevent_t, len(pids))
	for i, pid := range pids {
		unix.SetKevent(&changes[i], int(pid), unix.EVFILT_PROC, unix.EV_ADD|unix.EV_ONESHOT)
		changes[i].Fflags = unix.NOTE_EXIT
	}
	events := make([]unix.Kevent_t, len(pids))
	timeout := unix.NsecToTimespec(int64(time.Minute)) // only to notice cancellation
	remaining := len(pids)
	for remaining > 0 {
		n, err := unix.Kevent(kq, changes, events, &timeout)
		changes = nil // registered on the first call
		if errors.Is(err, unix.EINTR) {
			continue
		}
		if err != nil {
			return nil // ESRCH: the process is already gone
		}
		for _, ev := range events[:n] {
			if ev.Flags&unix.EV_ERROR != 0 || ev.Fflags&unix.NOTE_EXIT != 0 {
				remaining--
			}
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
	}
	return nil
}

// Launch opens the Rekordbox app bundle.
func Launch(app string) error {
	return exec.Command("open", "-a", app).Run()
}
