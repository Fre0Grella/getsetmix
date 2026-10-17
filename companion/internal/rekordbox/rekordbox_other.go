//go:build !windows && !darwin

package rekordbox

import (
	"context"
	"errors"
)

// Rekordbox ships for Windows and macOS only; these stubs keep the portable
// packages building and testable elsewhere (CI runs on Linux too).

func pioneerAppDir() string { return "" }

func findExe() string { return "" }

// Running reports no Rekordbox: there cannot be one on this OS.
func Running() ([]uint32, error) { return nil, nil }

func waitExit(context.Context, []uint32) error { return nil }

// Launch always fails on this OS.
func Launch(string) error { return errors.New("Rekordbox runs on Windows and macOS only") }
