//go:build !windows

package setup

import "os/exec"

func hideWindow(*exec.Cmd) {}
