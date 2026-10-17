//go:build !windows && !darwin

package install

import "errors"

var errUnsupported = errors.New("Rekordbox runs on Windows and macOS only")

// Install is not available on this OS.
func Install(Options) (Result, error) { return Result{}, errUnsupported }

// Uninstall is not available on this OS.
func Uninstall() (Result, error) { return Result{}, errUnsupported }

// InstallApp is not available on this OS.
func InstallApp(string, string) (Result, error) { return Result{}, errUnsupported }

// UninstallApp is not available on this OS.
func UninstallApp() (Result, error) { return Result{}, errUnsupported }
