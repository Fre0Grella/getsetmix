package install

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"golang.org/x/sys/windows/registry"
)

const (
	runKey   = `Software\Microsoft\Windows\CurrentVersion\Run`
	runValue = "GetSetMix Companion"
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

func shortcutPaths() []string {
	return []string{
		filepath.Join(os.Getenv("APPDATA"), `Microsoft\Windows\Start Menu\Programs`, LauncherName+".lnk"),
		filepath.Join(os.Getenv("USERPROFILE"), "Desktop", LauncherName+".lnk"),
	}
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
	for _, lnk := range shortcutPaths() {
		if err := makeShortcut(lnk, target, "launch", icon); err != nil {
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
	return res, nil
}

// Uninstall removes everything Install may have created.
func Uninstall() (Result, error) {
	var res Result
	for _, lnk := range shortcutPaths() {
		if err := os.Remove(lnk); err == nil {
			res.Created = append(res.Created, lnk)
		}
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
func makeShortcut(lnk, target, args, icon string) error {
	q := func(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }
	script := strings.Join([]string{
		"$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + q(lnk) + ")",
		"$s.TargetPath = " + q(target),
		"$s.Arguments = " + q(args),
		"$s.WorkingDirectory = " + q(filepath.Dir(target)),
		"$s.IconLocation = " + q(icon+",0"),
		"$s.Description = 'Import new GetSetMix tracks, then start Rekordbox'",
		"$s.Save()",
	}, "; ")
	out, err := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command", script).CombinedOutput()
	if err != nil {
		return errors.Join(err, errors.New(strings.TrimSpace(string(out))))
	}
	return nil
}
