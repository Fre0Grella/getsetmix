package install

import (
	"errors"
	"fmt"
	"html"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
	"unicode/utf16"

	"golang.org/x/sys/windows/registry"
)

const (
	runKey    = `Software\Microsoft\Windows\CurrentVersion\Run`
	runValue  = "GetSetMix Companion"
	fetchTask = "GetSetMix fetch new tracks" // top level: a folder would outlive the task
)

// guiExe is the windowless build shipped next to the console one
// (gsm-companionw.exe, like python/pythonw): shortcuts and autostart use it so
// no console window ever flashes up.
func guiExe(exe string) (string, bool) {
	ext := filepath.Ext(exe)
	w := strings.TrimSuffix(exe, ext)
	if !strings.HasSuffix(w, "w") {
		w += "w"
	}
	w += ext
	_, err := os.Stat(w)
	return w, err == nil
}

func shortcutPaths(name string) []string {
	return []string{
		filepath.Join(os.Getenv("APPDATA"), `Microsoft\Windows\Start Menu\Programs`, name+".lnk"),
		filepath.Join(os.Getenv("USERPROFILE"), "Desktop", name+".lnk"),
	}
}

// InstallApp creates the "GetSetMix" shortcuts that open the local app
// window (`exe --window`). Its console starts minimised: closing the window
// ends it.
func InstallApp(exe, _ string) (Result, error) {
	var res Result
	for _, lnk := range shortcutPaths(AppName) {
		if err := makeShortcut(lnk, exe, "--window", exe, "GetSetMix", true); err != nil {
			return res, fmt.Errorf("creating %s: %w", lnk, err)
		}
		res.Created = append(res.Created, lnk)
	}
	return res, nil
}

// UninstallApp removes what InstallApp created.
func UninstallApp() (Result, error) {
	var res Result
	for _, lnk := range shortcutPaths(AppName) {
		if os.Remove(lnk) == nil {
			res.Created = append(res.Created, lnk)
		}
	}
	return res, nil
}

// Install creates the launcher shortcuts and, optionally, the autostart entry.
func Install(o Options) (Result, error) {
	var res Result
	target, ok := guiExe(o.Exe)
	if !ok {
		target = o.Exe
		res.Notes = append(res.Notes, "gsm-companionw.exe is missing next to this program, "+
			"so a console window will flash when the launcher runs")
	}
	icon := o.RekordboxExe
	if icon == "" {
		icon = target
	}
	for _, lnk := range shortcutPaths(LauncherName) {
		if o.SkipLauncher {
			break
		}
		if err := makeShortcut(lnk, target, "launch", icon, "Import new GetSetMix tracks, then start Rekordbox", false); err != nil {
			return res, fmt.Errorf("creating %s: %w", lnk, err)
		}
		res.Created = append(res.Created, lnk)
	}
	if o.Autostart {
		k, _, err := registry.CreateKey(registry.CURRENT_USER, runKey, registry.SET_VALUE)
		if err != nil {
			return res, err
		}
		defer k.Close()
		if err := k.SetStringValue(runValue, fmt.Sprintf(`"%s" watch`, target)); err != nil {
			return res, err
		}
		res.Created = append(res.Created, `HKCU\`+runKey+`\`+runValue)
		res.Notes = append(res.Notes, "the watcher starts at your next sign-in; "+
			"run `gsm-companionw watch` to start it now")
	}
	if o.Fetch {
		if err := scheduleFetch(fetchTask, target, time.Now()); err != nil {
			return res, fmt.Errorf("scheduling fetch: %w", err)
		}
		res.Created = append(res.Created, "Task Scheduler: "+fetchTask)
	}
	return res, nil
}

// Uninstall removes everything Install may have created.
func Uninstall() (Result, error) {
	var res Result
	for _, lnk := range shortcutPaths(LauncherName) {
		if err := os.Remove(lnk); err == nil {
			res.Created = append(res.Created, lnk)
		}
	}
	if exec.Command("schtasks", "/Delete", "/F", "/TN", fetchTask).Run() == nil {
		res.Created = append(res.Created, "Task Scheduler: "+fetchTask)
	}
	k, err := registry.OpenKey(registry.CURRENT_USER, runKey, registry.SET_VALUE)
	if err == nil {
		defer k.Close()
		if k.DeleteValue(runValue) == nil {
			res.Created = append(res.Created, `HKCU\`+runKey+`\`+runValue)
		}
	}
	return res, nil
}

// makeShortcut writes a .lnk through the Windows Script Host — the only
// supported way to author one, and it only runs at install time.
func makeShortcut(lnk, target, args, icon, description string, minimized bool) error {
	style := "1"
	if minimized {
		style = "7"
	}
	q := func(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }
	script := strings.Join([]string{
		"$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + q(lnk) + ")",
		"$s.TargetPath = " + q(target),
		"$s.Arguments = " + q(args),
		"$s.WorkingDirectory = " + q(filepath.Dir(target)),
		"$s.IconLocation = " + q(icon+",0"),
		"$s.Description = " + q(description),
		"$s.WindowStyle = " + style,
		"$s.Save()",
	}, "; ")
	out, err := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command", script).CombinedOutput()
	if err != nil {
		return errors.Join(err, errors.New(strings.TrimSpace(string(out))))
	}
	return nil
}

// fetchTaskXML is the scheduled fetch. A plain `schtasks /SC MINUTE` task
// never starts on battery and stops when the power cable comes out, which on
// a DJ's laptop means never; this one runs on battery, catches up after
// sleep, waits for the network and never overlaps itself.
const fetchTaskXML = `<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Downloads new GetSetMix tracks and adds them to Rekordbox.</Description></RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition><Interval>PT%dM</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>%s</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>%s</Command><Arguments>fetch</Arguments></Exec></Actions>
</Task>
`

// scheduleFetch registers (or replaces) the per-user task name that runs
// `exe fetch` every FetchEvery minutes: no admin rights, no resident process.
func scheduleFetch(name, exe string, now time.Time) error {
	def := fmt.Sprintf(fetchTaskXML, FetchEvery, now.Format("2006-01-02T15:04:05"), html.EscapeString(exe))
	// schtasks reads task XML as UTF-16.
	u := utf16.Encode([]rune(def))
	buf := make([]byte, 2+2*len(u))
	buf[0], buf[1] = 0xFF, 0xFE
	for i, c := range u {
		buf[2+2*i], buf[3+2*i] = byte(c), byte(c>>8)
	}
	f, err := os.CreateTemp("", "gsm-fetch-task-*.xml")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	_, err = f.Write(buf)
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	if err != nil {
		return err
	}
	out, err := exec.Command("schtasks", "/Create", "/F", "/TN", name, "/XML", f.Name()).CombinedOutput()
	if err != nil {
		return fmt.Errorf("%v: %s", err, strings.TrimSpace(string(out)))
	}
	return nil
}
