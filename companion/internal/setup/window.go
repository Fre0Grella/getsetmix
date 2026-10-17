package setup

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
)

// appWindow opens url in a window of its own, without tabs or an address
// bar, using a Chromium browser's app mode (Edge ships with Windows). It
// returns a channel closed when the window is closed. With no such browser
// the url opens in the default browser and the channel is nil: the caller
// then relies on the page's heartbeat to know when it is gone.
func appWindow(ctx context.Context, url, profile string, width, height int) (<-chan struct{}, error) {
	exe := chromium()
	if exe == "" {
		return nil, openURL(url)
	}
	seedProfile(profile)
	cmd := exec.CommandContext(ctx, exe,
		"--app="+url,
		"--user-data-dir="+profile,
		"--window-size="+strconv.Itoa(width)+","+strconv.Itoa(height),
		"--no-first-run", "--no-default-browser-check",
		// Otherwise Edge stays alive in the background once the window
		// closes, and Setup would never notice.
		"--disable-background-mode",
		"--disable-sync",
		"--disable-features=Translate,msImplicitSignin,msEdgeSidebarV2,msHubApps,msEdgeStartupBoost",
	)
	if err := cmd.Start(); err != nil {
		return nil, openURL(url)
	}
	done := make(chan struct{})
	go func() { _ = cmd.Wait(); close(done) }()
	return done, nil
}

// seedProfile turns off what a fresh Edge profile would otherwise show over
// the window: signing in to the Windows account (a dialog that also blocks
// closing the window) and offering to translate the page.
func seedProfile(profile string) {
	prefs := filepath.Join(profile, "Default", "Preferences")
	if _, err := os.Stat(prefs); err == nil {
		return
	}
	_ = os.MkdirAll(filepath.Dir(prefs), 0o755)
	_ = os.WriteFile(prefs, []byte(`{"translate": {"enabled": false}, "signin": {"allowed": false}}`), 0o644)
}

// chromium finds a browser with an app mode: Edge, Chrome, Brave, Chromium.
func chromium() string {
	var candidates []string
	switch runtime.GOOS {
	case "windows":
		for _, base := range []string{os.Getenv("ProgramFiles(x86)"), os.Getenv("ProgramFiles"), os.Getenv("LOCALAPPDATA")} {
			if base == "" {
				continue
			}
			candidates = append(candidates,
				filepath.Join(base, `Microsoft\Edge\Application\msedge.exe`),
				filepath.Join(base, `Google\Chrome\Application\chrome.exe`),
				filepath.Join(base, `BraveSoftware\Brave-Browser\Application\brave.exe`),
			)
		}
	case "darwin":
		home, _ := os.UserHomeDir()
		for _, root := range []string{"/Applications", filepath.Join(home, "Applications")} {
			candidates = append(candidates,
				filepath.Join(root, "Google Chrome.app/Contents/MacOS/Google Chrome"),
				filepath.Join(root, "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
				filepath.Join(root, "Brave Browser.app/Contents/MacOS/Brave Browser"),
				filepath.Join(root, "Chromium.app/Contents/MacOS/Chromium"),
			)
		}
	default:
		for _, name := range []string{"google-chrome", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"} {
			if p, err := exec.LookPath(name); err == nil {
				candidates = append(candidates, p)
			}
		}
	}
	for _, c := range candidates {
		if info, err := os.Stat(c); err == nil && !info.IsDir() {
			return c
		}
	}
	return ""
}

// openURL opens url in the default browser.
func openURL(url string) error {
	switch runtime.GOOS {
	case "windows":
		return exec.Command("rundll32", "url.dll,FileProtocolHandler", url).Start()
	case "darwin":
		return exec.Command("open", url).Start()
	default:
		return exec.Command("xdg-open", url).Start()
	}
}

// openPath shows a folder or opens a file with its default program.
func openPath(path string) error {
	switch runtime.GOOS {
	case "windows":
		return exec.Command("explorer", path).Start()
	case "darwin":
		return exec.Command("open", path).Start()
	default:
		return exec.Command("xdg-open", path).Start()
	}
}
