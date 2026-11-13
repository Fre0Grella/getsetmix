package notices

import (
	"os"
	"strings"
	"testing"
)

func lf(s string) string { return strings.ReplaceAll(s, "\r\n", "\n") }

func TestEmbeddedTexts(t *testing.T) {
	if !strings.Contains(License(), "GNU AFFERO GENERAL PUBLIC LICENSE") {
		t.Error("License() is not the AGPL text")
	}
	if !strings.Contains(Notices(), "Third-party notices") {
		t.Error("Notices() is not THIRD-PARTY-NOTICES.md")
	}
	if all := Text(); !strings.Contains(all, "Third-party notices") || !strings.Contains(all, "AGPL-3.0-only") {
		t.Error("Text() misses the notices or the pointer to the AGPL text")
	}
}

// The embedded files are copies of the repository root's; a stale copy would
// ship out-of-date notices, so it fails here.
func TestCopiesMatchTheRepositoryRoot(t *testing.T) {
	for name, embedded := range map[string]string{"LICENSE": license, "THIRD-PARTY-NOTICES.md": thirdParty} {
		root, err := os.ReadFile("../../../" + name)
		if err != nil {
			t.Skipf("no repository root next to the module (%v)", err)
		}
		if lf(string(root)) != lf(embedded) {
			t.Errorf("%s differs from the repository root's: run `go generate ./internal/notices`", name)
		}
	}
}
