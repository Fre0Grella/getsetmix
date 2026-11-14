package recycle

import (
	"os"
	"path/filepath"
	"testing"
)

func TestMoveRefusesAFolderAndAMissingFile(t *testing.T) {
	dir := t.TempDir()
	if err := Move(dir); err == nil {
		t.Error("a folder was accepted")
	}
	if err := Move(filepath.Join(dir, "nothing.mp3")); err == nil {
		t.Error("a missing file was accepted")
	}
	if _, err := os.Stat(dir); err != nil {
		t.Errorf("the folder is gone: %v", err)
	}
}
