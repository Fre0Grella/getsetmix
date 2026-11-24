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
	"sort"
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
		tags := tagsOf(m)
		t.Title, t.Artist, t.Album, t.Genre, t.Comment, t.Year =
			tags.Title, tags.Artist, tags.Album, tags.Genre, tags.Comment, tags.Year
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

// ReadTags reads the six tag fields GetSetMix edits, read the way Probe reads
// them for an import. A file with no tags at all is an error.
func ReadTags(path string) (library.Tags, error) {
	f, err := os.Open(path)
	if err != nil {
		return library.Tags{}, err
	}
	defer f.Close()
	m, err := tag.ReadFrom(f)
	if err != nil {
		return library.Tags{}, err
	}
	return tagsOf(m), nil
}

// TagsOf is the six tag fields of a probed track.
func TagsOf(t library.Track) library.Tags {
	return library.Tags{Title: t.Title, Artist: t.Artist, Album: t.Album, Genre: t.Genre,
		Year: t.Year, Comment: t.Comment}
}

func tagsOf(m tag.Metadata) library.Tags {
	return library.Tags{
		Title:   clean(m.Title()),
		Artist:  clean(m.Artist()),
		Album:   clean(m.Album()),
		Genre:   clean(m.Genre()),
		Year:    m.Year(),
		Comment: clean(commentOf(m)),
	}
}

// commentOf is the file's comment, by the server's rule: in ID3 the COMM frame
// with no description, in English if there are several. The library alone
// takes whichever frame comes first and may answer with its description
// ("iTunNORM"), and a tag rewrite can reorder the frames, which would look
// like a changed comment.
func commentOf(m tag.Metadata) string {
	switch m.Format() {
	case tag.ID3v2_2, tag.ID3v2_3, tag.ID3v2_4:
	default:
		return m.Comment()
	}
	raw := m.Raw()
	names := make([]string, 0, len(raw))
	for name := range raw {
		names = append(names, name)
	}
	sort.Strings(names)
	found, foundEnglish := "", false
	for _, name := range names {
		c, ok := raw[name].(*tag.Comm)
		if !ok {
			continue
		}
		// A frame without the separator parses with its text as the description.
		text := c.Text
		if c.Description != "" {
			if c.Text != "" {
				continue
			}
			text = c.Description
		}
		if english := c.Language == "eng"; found == "" || (english && !foundEnglish) {
			found, foundEnglish = text, english
		}
	}
	return strings.TrimSpace(strings.Trim(found, "\x00"))
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
