package layers

import (
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

const module = "github.com/Fre0Grella/getsetmix/companion/internal/"

// The packages that must build and test without SQLCipher: they read files,
// talk to the server or keep the companion's memory, and only importer,
// setup and cmd write master.db.
var pure = []string{"track", "track/tracktest", "audio", "scan", "fetch", "config",
	"ledger", "ledger/ledgertest"}

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
// the audio reader, the scanner, fetch, the settings and the ledger never
// depend on the SQLCipher package or its driver.
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

// TestConfigIsSettingsOnly protects config as companion.json alone: what the
// companion remembers is the ledger's, so config needs none of the rest.
func TestConfigIsSettingsOnly(t *testing.T) {
	for _, dep := range deps(t, "config") {
		dep = strings.Fields(dep)[0]
		if strings.HasPrefix(dep, module) && dep != module+"config" && dep != module+"atomicfile" {
			t.Errorf("config depends on %s", dep)
		}
	}
}

// stateFiles matches a string literal naming one of the ledger's files.
var stateFiles = regexp.MustCompile(`"[^"]*(fetched\.json|fetched\.v1\.json|state\.json|fetch\.lock|sync\.lock)[^"]*"`)

// TestOnlyTheLedgerNamesTheStateFiles protects the ledger as the one owner
// of fetched.json, state.json and their locks: code anywhere else that
// names them reads or writes them behind its back. Tests may name them, to
// check what is on disk.
func TestOnlyTheLedgerNamesTheStateFiles(t *testing.T) {
	err := filepath.WalkDir("../..", func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() && filepath.ToSlash(p) == "../../internal/ledger" {
			return filepath.SkipDir
		}
		if d.IsDir() || !strings.HasSuffix(p, ".go") || strings.HasSuffix(p, "_test.go") {
			return nil
		}
		data, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		for i, line := range strings.Split(string(data), "\n") {
			if code, _, _ := strings.Cut(line, "//"); stateFiles.MatchString(code) {
				t.Errorf("%s:%d names a ledger file: %s", filepath.ToSlash(p), i+1, strings.TrimSpace(line))
			}
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}
