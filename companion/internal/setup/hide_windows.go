package setup

import (
	"os/exec"
	"syscall"
)

// hideWindow keeps a helper console (PowerShell) from flashing up.
func hideWindow(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000} // CREATE_NO_WINDOW
}
