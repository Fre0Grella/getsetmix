package atomicfile

import (
	"errors"
	"io"
	"os"
	"path/filepath"
	"testing"
)

func TestWriteFileReplacesTheTargetAndLeavesNoTemporaryFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "state.json")
	if err := os.WriteFile(path, []byte("old"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := WriteFile(path, []byte("new"), 0o644); err != nil {
		t.Fatal(err)
	}
	if got, _ := os.ReadFile(path); string(got) != "new" {
		t.Fatalf("content = %q, want %q", got, "new")
	}
	if entries, _ := os.ReadDir(dir); len(entries) != 1 {
		t.Fatalf("folder holds %d entries, want only the target", len(entries))
	}
}

func TestAFailedWriteKeepsTheOldFileAndRemovesTheTemporaryOne(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "master.db")
	if err := os.WriteFile(path, []byte("old"), 0o644); err != nil {
		t.Fatal(err)
	}
	boom := errors.New("disk full")
	err := Write(path, 0o644, func(w io.Writer) error {
		_, _ = w.Write([]byte("half"))
		return boom
	})
	if !errors.Is(err, boom) {
		t.Fatalf("err = %v, want %v", err, boom)
	}
	if got, _ := os.ReadFile(path); string(got) != "old" {
		t.Fatalf("content = %q, want the old file intact", got)
	}
	if entries, _ := os.ReadDir(dir); len(entries) != 1 {
		t.Fatalf("folder holds %d entries, want the temporary file removed", len(entries))
	}
}
