package track

import "strconv"

// Tags are the six tag fields GetSetMix edits on the server
// (docs/design/library.md, 3.6), as a file holds them.
type Tags struct {
	Title   string `json:"title"`
	Artist  string `json:"artist"`
	Album   string `json:"album"`
	Genre   string `json:"genre"`
	Year    int    `json:"year,omitempty"`
	Comment string `json:"comment"`
}

// The six fields, by the names Changed reports.
const (
	FieldTitle   = "title"
	FieldArtist  = "artist"
	FieldAlbum   = "album"
	FieldGenre   = "genre"
	FieldYear    = "year"
	FieldComment = "comment"
)

// AllFields is every field, for a change with nothing to compare against.
var AllFields = []string{FieldTitle, FieldArtist, FieldAlbum, FieldGenre, FieldYear, FieldComment}

// Changed lists the fields whose values differ between was and now, in
// AllFields order. A nil was means nothing is known to compare with: every
// field counts as changed.
func Changed(was *Tags, now Tags) []string {
	if was == nil {
		return append([]string(nil), AllFields...)
	}
	var out []string
	for _, f := range AllFields {
		if was.value(f) != now.value(f) {
			out = append(out, f)
		}
	}
	return out
}

func (t Tags) value(field string) string {
	switch field {
	case FieldTitle:
		return t.Title
	case FieldArtist:
		return t.Artist
	case FieldAlbum:
		return t.Album
	case FieldGenre:
		return t.Genre
	case FieldYear:
		return strconv.Itoa(t.Year)
	case FieldComment:
		return t.Comment
	}
	return ""
}
