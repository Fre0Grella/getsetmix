package librarytest

import "bytes"

// Tags are what MP3 writes into its ID3v2.4 tag; empty fields are left out.
type Tags struct {
	Title, Artist, Album, Genre, Year, Comment string
}

// MP3 is a small valid MPEG-1 Layer III stream (20 frames, 320 kbps) under
// an ID3v2.4 tag holding tags. seed changes the audio, so two seeds are two
// tracks and one seed with other tags is the same track edited.
func MP3(seed byte, tags Tags) []byte {
	frame := make([]byte, 1044)
	copy(frame, []byte{0xff, 0xfb, 0xe0, 0x00})
	frame[100] = seed
	audio := bytes.Repeat(frame, 20)

	var frames bytes.Buffer
	text := func(id, value string) {
		if value == "" {
			return
		}
		writeFrame(&frames, id, append([]byte{3}, value...))
	}
	text("TIT2", tags.Title)
	text("TPE1", tags.Artist)
	text("TALB", tags.Album)
	text("TCON", tags.Genre)
	text("TDRC", tags.Year)
	if tags.Comment != "" {
		writeFrame(&frames, "COMM", append([]byte{3, 'e', 'n', 'g', 0}, tags.Comment...))
	}
	var out bytes.Buffer
	out.WriteString("ID3")
	out.Write([]byte{4, 0, 0})
	out.Write(syncsafe(frames.Len()))
	out.Write(frames.Bytes())
	out.Write(audio)
	return out.Bytes()
}

func writeFrame(w *bytes.Buffer, id string, data []byte) {
	w.WriteString(id)
	w.Write(syncsafe(len(data)))
	w.Write([]byte{0, 0})
	w.Write(data)
}

func syncsafe(n int) []byte {
	return []byte{byte(n >> 21 & 0x7f), byte(n >> 14 & 0x7f), byte(n >> 7 & 0x7f), byte(n & 0x7f)}
}
