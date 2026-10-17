// Package audio reads what Rekordbox's collection needs from an audio file:
// tags (title, artist, album, genre, comment) and the stream facts shown in
// its track list (length, bit rate, bit depth, sample rate).
//
// Stream facts are parsed from the container headers directly — a few hundred
// bytes per file, no decoder. Rekordbox re-reads all of it when it analyses
// the track, so a value we cannot determine is left empty, never guessed.
package audio

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/dhowden/tag"

	"github.com/Fre0Grella/getsetmix/companion/internal/library"
)

// Extensions Rekordbox imports, mapped to its FileType codes.
var Extensions = map[string]int{
	".mp3":  library.FileMP3,
	".m4a":  library.FileM4A,
	".aac":  library.FileM4A,
	".flac": library.FileFLAC,
	".wav":  library.FileWAV,
	".aif":  library.FileAIFF,
	".aiff": library.FileAIFF,
}

// Supported reports whether Rekordbox can import a file with this name.
func Supported(name string) bool {
	_, ok := Extensions[strings.ToLower(filepath.Ext(name))]
	return ok
}

// stream holds the technical facts parsed from the container.
type stream struct {
	seconds    float64
	bitRate    int // kbps
	bitDepth   int
	sampleRate int
	alac       bool
}

// Probe builds the library.Track for the file at path.
func Probe(path string) (library.Track, error) {
	fileType, ok := Extensions[strings.ToLower(filepath.Ext(path))]
	if !ok {
		return library.Track{}, fmt.Errorf("unsupported file type %q", filepath.Ext(path))
	}
	f, err := os.Open(path)
	if err != nil {
		return library.Track{}, err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return library.Track{}, err
	}

	t := library.Track{Path: path, FileType: fileType, FileSize: info.Size()}
	t.FileID, _ = fileID(f)

	if m, err := tag.ReadFrom(f); err == nil {
		t.Title = clean(m.Title())
		t.Artist = clean(m.Artist())
		t.Album = clean(m.Album())
		t.Genre = clean(m.Genre())
		t.Comment = clean(m.Comment())
		t.Year = m.Year()
		t.TrackNo, _ = m.Track()
	}

	if _, err := f.Seek(0, io.SeekStart); err != nil {
		return t, err
	}
	var s stream
	switch fileType {
	case library.FileMP3:
		s, err = probeMP3(f, info.Size())
	case library.FileFLAC:
		s, err = probeFLAC(f)
	case library.FileWAV:
		s, err = probeWAV(f)
	case library.FileAIFF:
		s, err = probeAIFF(f)
	case library.FileM4A:
		s, err = probeMP4(f, info.Size())
		if s.alac {
			t.FileType = library.FileALAC
		}
	}
	if err != nil {
		// Unreadable stream facts are not fatal: Rekordbox fills them in on
		// analysis. A file that is not audio at all fails here, though.
		if s == (stream{}) && t.Title == "" {
			return t, fmt.Errorf("not a readable audio file: %w", err)
		}
	}
	t.Length = int(s.seconds)
	t.BitRate = s.bitRate
	t.BitDepth = s.bitDepth
	t.SampleRate = s.sampleRate
	return t, nil
}

// clean drops NUL padding but otherwise keeps tag text verbatim: Rekordbox
// stores it as is, leading and trailing spaces included.
func clean(s string) string {
	s = strings.ReplaceAll(s, "\x00", "")
	if strings.TrimSpace(s) == "" {
		return ""
	}
	return s
}
