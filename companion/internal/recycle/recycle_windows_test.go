package recycle

import (
	"bytes"
	"crypto/rand"
	"os"
	"path/filepath"
	"testing"

	"golang.org/x/sys/windows"
)

// The real Recycle Bin, with a temporary file only: it is found there by its
// random content and then taken out again, so the bin is left as it was.
// Opt-in on a desktop (it touches the user's Recycle Bin), always on in CI.
func TestMoveSendsATemporaryFileToTheRecycleBin(t *testing.T) {
	if os.Getenv("CI") == "" && os.Getenv("GSM_TEST_RECYCLE") == "" {
		t.Skip("set GSM_TEST_RECYCLE=1 to use this computer's Recycle Bin")
	}
	content := make([]byte, 4096)
	rand.Read(content)
	path := filepath.Join(t.TempDir(), "gsm-recycle-test.mp3")
	if err := os.WriteFile(path, content, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := Move(path); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("the file is still there: %v", err)
	}

	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err != nil {
		t.Fatal(err)
	}
	bin := filepath.Join(filepath.VolumeName(path)+`\`, "$Recycle.Bin", user.User.Sid.String())
	found, _ := filepath.Glob(filepath.Join(bin, "$R*.mp3"))
	for _, f := range found {
		data, err := os.ReadFile(f)
		if err != nil || !bytes.Equal(data, content) {
			continue
		}
		// $R… holds the bytes, $I… the original path: remove both.
		os.Remove(f)
		os.Remove(filepath.Join(bin, "$I"+filepath.Base(f)[2:]))
		return
	}
	t.Fatalf("the file is not in %s (deleted for good?)", bin)
}
