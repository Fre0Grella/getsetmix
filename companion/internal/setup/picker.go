package setup

import (
	"errors"
	"os/exec"
	"runtime"
	"strings"
)

// errCancelled means the person closed the folder dialog.
var errCancelled = errors.New("cancelled")

// pickFolder shows the system's folder dialog, starting at start.
func pickFolder(prompt, start string) (string, error) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		q := func(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }
		// An owner form that is TopMost keeps the dialog in front of the
		// setup window instead of behind it.
		script := strings.Join([]string{
			"Add-Type -AssemblyName System.Windows.Forms",
			"$f = New-Object System.Windows.Forms.Form -Property @{TopMost = $true; ShowInTaskbar = $false}",
			"$d = New-Object System.Windows.Forms.FolderBrowserDialog",
			"$d.Description = " + q(prompt),
			"$d.ShowNewFolderButton = $true",
			"$d.SelectedPath = " + q(start),
			"if ($d.ShowDialog($f) -eq 'OK') { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $d.SelectedPath }",
		}, "; ")
		cmd = exec.Command("powershell", "-NoProfile", "-NonInteractive", "-STA", "-Command", script)
		hideWindow(cmd)
	case "darwin":
		as := `POSIX path of (choose folder with prompt ` + appleQuote(prompt)
		if start != "" {
			as += ` default location (POSIX file ` + appleQuote(start) + `)`
		}
		as += `)`
		cmd = exec.Command("osascript", "-e", as)
	default:
		cmd = exec.Command("zenity", "--file-selection", "--directory", "--title="+prompt, "--filename="+start+"/")
	}
	out, err := cmd.Output()
	path := strings.TrimRight(strings.TrimSpace(string(out)), "/\\")
	if runtime.GOOS != "windows" && strings.HasPrefix(strings.TrimSpace(string(out)), "/") && path == "" {
		path = "/"
	}
	if path == "" {
		if err != nil && runtime.GOOS == "windows" {
			return "", err
		}
		return "", errCancelled
	}
	return path, nil
}

func appleQuote(s string) string {
	return `"` + strings.ReplaceAll(strings.ReplaceAll(s, `\`, `\\`), `"`, `\"`) + `"`
}
