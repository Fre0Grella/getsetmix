package audio

import "testing"

func syncsafe(n int) []byte {
	return []byte{byte(n >> 21 & 0x7f), byte(n >> 14 & 0x7f), byte(n >> 7 & 0x7f), byte(n & 0x7f)}
}

func commFrame(lang, desc, text string) []byte {
	body := append([]byte{3}, lang...)
	body = append(append(body, desc...), 0)
	body = append(body, text...)
	return append(append([]byte("COMM"), append(syncsafe(len(body)), 0, 0)...), body...)
}

// The comment is the frame with no description, whatever order a tagger wrote
// the frames in; a frame with a description is not the comment.
func TestCommentIsTheFrameWithoutADescription(t *testing.T) {
	for name, c := range map[string]struct {
		frames [][]byte
		want   string
	}{
		"described first": {[][]byte{commFrame("eng", "iTunNORM", "0000"), commFrame("eng", "", "mine")}, "mine"},
		"english wins":    {[][]byte{commFrame("ita", "", "mio"), commFrame("eng", "", "mine")}, "mine"},
		"other language":  {[][]byte{commFrame("ita", "", "mio")}, "mio"},
		"only described":  {[][]byte{commFrame("eng", "iTunNORM", "0000")}, ""},
	} {
		var all []byte
		for _, f := range c.frames {
			all = append(all, f...)
		}
		data := append(append([]byte{'I', 'D', '3', 4, 0, 0}, syncsafe(len(all))...), all...)
		got, err := ReadTags(write(t, "a.mp3", append(data, make([]byte, 64)...)))
		if err != nil || got.Comment != c.want {
			t.Errorf("%s: comment %q, want %q (%v)", name, got.Comment, c.want, err)
		}
	}
}
