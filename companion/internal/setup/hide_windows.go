package setup

import (
	"os/exec"
	"syscall"
)

const createNoWindow = 0x08000000

// hideWindow keeps a helper (PowerShell, the app) from showing any window.
func hideWindow(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
}

// noConsole keeps a helper's console from flashing up while letting the
// windows it opens show normally.
func noConsole(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: createNoWindow}
}
