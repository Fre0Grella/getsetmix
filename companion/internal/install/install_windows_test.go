package install

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Creates and deletes a real scheduled task: opt in with GSM_TEST_SCHTASKS=1.
func TestScheduleFetchRunsOnBattery(t *testing.T) {
	if os.Getenv("GSM_TEST_SCHTASKS") != "1" {
		t.Skip("set GSM_TEST_SCHTASKS=1 to create (and delete) a real scheduled task")
	}
	name := "GetSetMixTestFetchProbe" // top level: a folder would outlive the task
	exe := `C:\Program Files\Some & Folder\gsm-companionw.exe`
	if err := scheduleFetch(name, exe, time.Now()); err != nil {
		t.Fatal(err)
	}
	defer exec.Command("schtasks", "/Delete", "/F", "/TN", name).Run()
	out, err := exec.Command("schtasks", "/Query", "/TN", name, "/XML").Output()
	if err != nil {
		t.Fatal(err)
	}
	xml := strings.ReplaceAll(string(out), "\x00", "")
	for _, want := range []string{
		"<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>",
		"<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>",
		"<StartWhenAvailable>true</StartWhenAvailable>",
		"<Interval>PT15M</Interval>",
		`<Command>C:\Program Files\Some &amp; Folder\gsm-companionw.exe</Command>`,
		"<Arguments>fetch</Arguments>",
	} {
		if !strings.Contains(xml, want) {
			t.Errorf("task lacks %s", want)
		}
	}
}

// Writes a real .lnk into a temp folder and reads it back through the
// Windows Script Host, the reference reader for shortcuts.
func TestMakeShortcutRoundTrip(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "Mix è & O'Brien")
	if err := os.Mkdir(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(dir, "gsm-companionw.exe")
	if err := os.WriteFile(target, nil, 0o755); err != nil {
		t.Fatal(err)
	}
	for _, minimized := range []bool{false, true} {
		lnk := filepath.Join(dir, fmt.Sprintf("Rekordbox (GetSetMix) %v.lnk", minimized))
		if err := makeShortcut(lnk, target, "launch", target, "Import new tracks", minimized); err != nil {
			t.Fatal(err)
		}
		script := `[Console]::OutputEncoding = [Text.Encoding]::UTF8
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:GSM_LNK)
$s.TargetPath; $s.Arguments; $s.WorkingDirectory; $s.Description; $s.IconLocation; $s.WindowStyle`
		cmd := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command", script)
		cmd.Env = append(os.Environ(), "GSM_LNK="+lnk)
		out, err := cmd.Output()
		if err != nil {
			t.Fatal(err)
		}
		style := "1"
		if minimized {
			style = "7"
		}
		got := strings.Split(strings.TrimSpace(strings.ReplaceAll(string(out), "\r", "")), "\n")
		want := []string{target, "launch", dir, "Import new tracks", target + ",0", style}
		if strings.Join(got, "|") != strings.Join(want, "|") {
			t.Errorf("shortcut reads back as\n%q\nwant\n%q", got, want)
		}
	}
}
