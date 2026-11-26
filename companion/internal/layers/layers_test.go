package layers

import (
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

const module = "github.com/Fre0Grella/getsetmix/companion/internal/"

// The packages that must build and test without SQLCipher: they read files or
// talk to the server, and only importer, setup and cmd write master.db.
var pure = []string{"track", "track/tracktest", "audio", "scan", "fetch", "config"}

// forbidden are the packages a pure package may not reach, even from a test.
var forbidden = []string{module + "library", "github.com/mutecomm/go-sqlcipher"}

// deps lists every package pkg needs, its tests' imports included, one per
// line; a package built for a test reads "p [p.test]".
func deps(t *testing.T, pkg string) []string {
	t.Helper()
	watchSources(t)
	out, err := exec.Command("go", "list", "-deps", "-test", module+pkg).Output()
	if err != nil {
		t.Fatalf("go list %s: %v", pkg, err)
	}
	return strings.Split(strings.TrimSpace(string(out)), "\n")
}

// watchSources stats every Go file and go.mod of the module. go list runs
// outside the test, so without this the test cache would keep a pass after
// an import changed; it reruns the test when a file it stated changes.
func watchSources(t *testing.T) {
	t.Helper()
	err := filepath.WalkDir("../..", func(p string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}
		if strings.HasSuffix(p, ".go") || d.Name() == "go.mod" {
			_, err = os.Stat(p)
		}
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
}

// TestPurePackagesSkipTheDatabase protects the rule that the track types,
// the audio reader, the scanner, fetch and the settings never depend on the
// SQLCipher package or its driver.
func TestPurePackagesSkipTheDatabase(t *testing.T) {
	for _, pkg := range pure {
		for _, dep := range deps(t, pkg) {
			for _, f := range forbidden {
				if strings.HasPrefix(dep, f) {
					t.Errorf("%s depends on %s", pkg, dep)
				}
			}
		}
	}
}

// TestTrackImportsNothingOfTheCompanion protects track as the bottom layer:
// every other package may use it, so it may use none of them.
func TestTrackImportsNothingOfTheCompanion(t *testing.T) {
	for _, dep := range deps(t, "track") {
		dep = strings.Fields(dep)[0]
		if strings.HasPrefix(dep, module) && !strings.HasPrefix(dep, module+"track") {
			t.Errorf("track depends on %s", dep)
		}
	}
}
