package install

import (
	"fmt"
	"html"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const agentLabel = "com.getsetmix.companion"

func appPath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, "Applications", LauncherName+".app")
}

func agentPath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, "Library", "LaunchAgents", agentLabel+".plist")
}

// Install creates the launcher app and, optionally, the launchd agent.
func Install(o Options) (Result, error) {
	var res Result
	app := appPath()
	macos := filepath.Join(app, "Contents", "MacOS")
	if err := os.MkdirAll(macos, 0o755); err != nil {
		return res, err
	}
	script := "#!/bin/sh\nexec " + shellQuote(o.Exe) + " launch\n"
	if err := os.WriteFile(filepath.Join(macos, "launch"), []byte(script), 0o755); err != nil {
		return res, err
	}
	icon := ""
	if o.RekordboxExe != "" { // borrow Rekordbox's icon so the launcher looks like it
		if icns, _ := filepath.Glob(filepath.Join(o.RekordboxExe, "Contents", "Resources", "*.icns")); len(icns) > 0 {
			resources := filepath.Join(app, "Contents", "Resources")
			if os.MkdirAll(resources, 0o755) == nil && copyFile(icns[0], filepath.Join(resources, "app.icns")) == nil {
				icon = "<key>CFBundleIconFile</key><string>app</string>"
			}
		}
	}
	plist := fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>%s</string>
<key>CFBundleIdentifier</key><string>com.getsetmix.launcher</string>
<key>CFBundleExecutable</key><string>launch</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSUIElement</key><true/>
%s
</dict></plist>
`, html.EscapeString(LauncherName), icon)
	if err := os.WriteFile(filepath.Join(app, "Contents", "Info.plist"), []byte(plist), 0o644); err != nil {
		return res, err
	}
	res.Created = append(res.Created, app)

	if o.Autostart {
		// launchd watches the folders and starts a one-shot sync when they
		// change; `--wait` lets that sync outlast an open Rekordbox. Nothing
		// of ours runs in between.
		var paths strings.Builder
		for _, f := range o.Folders {
			paths.WriteString("<string>" + html.EscapeString(f) + "</string>")
		}
		agent := fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>%s</string>
<key>ProgramArguments</key><array><string>%s</string><string>sync</string><string>--wait</string></array>
<key>WatchPaths</key><array>%s</array>
<key>RunAtLoad</key><true/>
<key>ThrottleInterval</key><integer>15</integer>
<key>ProcessType</key><string>Background</string>
<key>LowPriorityIO</key><true/>
</dict></plist>
`, agentLabel, html.EscapeString(o.Exe), paths.String())
		path := agentPath()
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return res, err
		}
		if err := os.WriteFile(path, []byte(agent), 0o644); err != nil {
			return res, err
		}
		_ = exec.Command("launchctl", "unload", path).Run()
		if out, err := exec.Command("launchctl", "load", path).CombinedOutput(); err != nil {
			return res, fmt.Errorf("launchctl load: %v: %s", err, out)
		}
		res.Created = append(res.Created, path)
	}
	res.Notes = append(res.Notes, "macOS may ask once whether to open a program from the internet: "+
		"right-click it > Open, or run `xattr -d com.apple.quarantine "+o.Exe+"`")
	return res, nil
}

// Uninstall removes everything Install may have created.
func Uninstall() (Result, error) {
	var res Result
	if err := os.RemoveAll(appPath()); err == nil {
		res.Created = append(res.Created, appPath())
	}
	if _, err := os.Stat(agentPath()); err == nil {
		_ = exec.Command("launchctl", "unload", agentPath()).Run()
		if os.Remove(agentPath()) == nil {
			res.Created = append(res.Created, agentPath())
		}
	}
	return res, nil
}

func shellQuote(s string) string {
	return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'"
}

func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0o644)
}
