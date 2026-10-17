package install

import (
	"os"
	"os/exec"
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
