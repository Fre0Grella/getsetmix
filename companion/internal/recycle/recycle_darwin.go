package recycle

import (
	"fmt"
	"os/exec"
	"strings"
)

// move asks the Finder to move the file to the Trash, which keeps "Put Back"
// working. The first time, macOS asks whether GetSetMix may control the
// Finder; without that permission the move fails and the file stays.
func move(abs string) error {
	out, err := exec.Command("osascript",
		"-e", "on run argv",
		"-e", `tell application "Finder" to delete (POSIX file (item 1 of argv) as alias)`,
		"-e", "end run",
		abs).CombinedOutput()
	if err != nil {
		return fmt.Errorf("moving to the Trash failed: %v %s", err, strings.TrimSpace(string(out)))
	}
	return nil
}
