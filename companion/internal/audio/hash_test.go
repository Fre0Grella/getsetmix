package audio

import (
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"
)

// The fixtures are shared with the Python implementation (app/audiohash.py):
// testdata/audiohash at the repository root, one level above this module.
func fixtures(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			break
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("go.mod not found above the test")
		}
		dir = parent
	}
	root := filepath.Join(filepath.Dir(dir), "testdata", "audiohash")
	if _, err := os.Stat(filepath.Join(root, "expected.json")); err != nil {
		t.Skipf("shared fixtures not found at %s: the companion module is not inside "+
			"the GetSetMix repository here, so the audio id cannot be checked", root)
	}
	return root
}

type expectedIDs struct {
	Version   int                 `json:"version"`
	Files     map[string]string   `json:"files"`
	Same      map[string][]string `json:"same"`
	Different [][]string          `json:"different"`
}

func loadExpected(t *testing.T) (string, expectedIDs) {
	root := fixtures(t)
	data, err := os.ReadFile(filepath.Join(root, "expected.json"))
	if err != nil {
		t.Fatal(err)
	}
	var e expectedIDs
	if err := json.Unmarshal(data, &e); err != nil {
		t.Fatal(err)
	}
	if e.Version != 1 || len(e.Files) == 0 {
		t.Fatalf("unexpected expected.json: version %d, %d files", e.Version, len(e.Files))
	}
	return root, e
}

func TestEveryFixtureGetsItsExpectedID(t *testing.T) {
	root, e := loadExpected(t)
	names := make([]string, 0, len(e.Files))
	for rel := range e.Files {
		names = append(names, rel)
	}
	sort.Strings(names)
	for _, rel := range names {
		got, err := ID(filepath.Join(root, filepath.FromSlash(rel)))
		if err != nil {
			t.Errorf("%s: %v", rel, err)
			continue
		}
		if got != e.Files[rel] {
			t.Errorf("%s: got %s, want %s", rel, got, e.Files[rel])
		}
	}
}

func TestSameAudioSharesOneID(t *testing.T) {
	root, e := loadExpected(t)
	for group, files := range e.Same {
		ids := map[string]bool{}
		for _, rel := range files {
			id, err := ID(filepath.Join(root, filepath.FromSlash(rel)))
			if err != nil {
				t.Fatalf("%s: %v", rel, err)
			}
			ids[id] = true
		}
		if len(ids) != 1 {
			t.Errorf("group %s: %d different ids", group, len(ids))
		}
	}
}

func TestDifferentAudioGetsDifferentIDs(t *testing.T) {
	root, e := loadExpected(t)
	for _, files := range e.Different {
		seen := map[string]string{}
		for _, rel := range files {
			id, err := ID(filepath.Join(root, filepath.FromSlash(rel)))
			if err != nil {
				t.Fatalf("%s: %v", rel, err)
			}
			if other, dup := seen[id]; dup {
				t.Errorf("%s and %s share %s", other, rel, id)
			}
			seen[id] = rel
		}
	}
}

var idShape = regexp.MustCompile(`^(a1|f1)_[0-9a-f]{32}$`)

// Damaged files never fail: every prefix of every fixture gets an id of the
// right shape (the fallback when the header or tag region is cut).
func TestTruncatedFilesNeverFail(t *testing.T) {
	root, e := loadExpected(t)
	dir := t.TempDir()
	for rel := range e.Files {
		data, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(rel)))
		if err != nil {
			t.Fatal(err)
		}
		for _, cut := range []int{0, 1, 3, 7, 10, 12, 31, 100, len(data) / 2, len(data) - 1} {
			if cut < 0 || cut > len(data) {
				continue
			}
			p := filepath.Join(dir, strings.ReplaceAll(rel, "/", "_"))
			if err := os.WriteFile(p, data[:cut], 0o644); err != nil {
				t.Fatal(err)
			}
			id, err := ID(p)
			if err != nil || !idShape.MatchString(id) {
				t.Errorf("%s cut at %d: %q %v", rel, cut, id, err)
			}
		}
	}
}

func TestMissingFileIsAnError(t *testing.T) {
	if _, err := ID(filepath.Join(t.TempDir(), "nope.mp3")); err == nil {
		t.Fatal("no error for a missing file")
	}
}

func TestIsFallback(t *testing.T) {
	if !IsFallback("f1_00000000000000000000000000000000") || IsFallback("a1_00000000000000000000000000000000") {
		t.Fatal("IsFallback")
	}
}
