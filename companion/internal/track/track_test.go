package track_test

import (
	"path/filepath"
	"slices"
	"testing"

	"github.com/Fre0Grella/getsetmix/companion/internal/track"
)

// Changed names the fields that differ, in AllFields order; with nothing
// to compare against, every field.
func TestChangedNamesTheFieldsThatDiffer(t *testing.T) {
	was := track.Tags{Title: "A", Artist: "B", Genre: "House", Year: 2019, Comment: "c"}
	now := was
	if got := track.Changed(&was, now); len(got) != 0 {
		t.Fatalf("no change: %v", got)
	}
	now.Genre, now.Year, now.Album = "Tech House", 0, "X"
	if got := track.Changed(&was, now); !slices.Equal(got, []string{"album", "genre", "year"}) {
		t.Fatalf("changed %v", got)
	}
	if got := track.Changed(nil, now); !slices.Equal(got, track.AllFields) {
		t.Fatalf("nothing known: %v", got)
	}
}

// One file, however its path is written, has one key.
func TestPathKeyIgnoresSlashesCaseAndNormalisation(t *testing.T) {
	nfd := "Bee\u0301le.mp3" // macOS hands out decomposed names
	if track.PathKey(filepath.FromSlash("C:/Music/BEÉLE.mp3")) != track.PathKey("c:/music/"+nfd) {
		t.Fatal("path keys should match across slashes, case and normalisation")
	}
}

// A server path never lands outside the folder.
func TestLocalRefusesEscapes(t *testing.T) {
	for _, bad := range []string{"../x.mp3", "/etc/x.mp3", "a/../../x.mp3", `a\..\x.mp3`, "", "./x.mp3"} {
		if _, err := track.Local("/music", bad); err == nil {
			t.Errorf("%q accepted", bad)
		}
	}
	if p, err := track.Local("dl", "House/x.mp3"); err != nil || p != filepath.Join("dl", "House", "x.mp3") {
		t.Errorf("got %q %v", p, err)
	}
}
