package audio

import (
	"bytes"
	"encoding/binary"
	"math"
	"os"
	"path/filepath"
	"testing"

	"github.com/Fre0Grella/getsetmix/companion/internal/library"
)

func write(t *testing.T, name string, data []byte) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

// id3 builds an ID3v2.3 tag with text frames.
func id3(frames map[string]string) []byte {
	var body bytes.Buffer
	for id, text := range frames {
		payload := append([]byte{0}, text...) // ISO-8859-1
		body.WriteString(id)
		binary.Write(&body, binary.BigEndian, uint32(len(payload)))
		body.Write([]byte{0, 0})
		body.Write(payload)
	}
	n := body.Len()
	head := []byte{'I', 'D', '3', 3, 0, 0,
		byte(n >> 21 & 0x7f), byte(n >> 14 & 0x7f), byte(n >> 7 & 0x7f), byte(n & 0x7f)}
	return append(head, body.Bytes()...)
}

// mp3Frames returns n MPEG-1 Layer III stereo frames at 320 kbps / 44.1 kHz.
// With xing, the first frame carries a Xing header claiming vbrFrames frames.
func mp3Frames(n int, xing string, vbrFrames uint32) []byte {
	const frameLen = 144 * 320000 / 44100 // 1044 bytes
	var out bytes.Buffer
	for i := range n {
		f := make([]byte, frameLen)
		copy(f, []byte{0xff, 0xfb, 0xe0, 0x00}) // sync, MPEG1 L3, 320k, 44.1k, stereo
		if i == 0 && xing != "" {
			at := 4 + 32
			copy(f[at:], xing)
			binary.BigEndian.PutUint32(f[at+4:], 1) // frames field present
			binary.BigEndian.PutUint32(f[at+8:], vbrFrames)
		}
		out.Write(f)
	}
	return out.Bytes()
}

func TestProbeMP3CBR(t *testing.T) {
	data := append(id3(map[string]string{"TIT2": "La Plena", "TPE1": "W Sound", "TCON": "Reggaeton"}),
		mp3Frames(200, "", 0)...)
	tr, err := Probe(write(t, "La Plena.mp3", data))
	if err != nil {
		t.Fatal(err)
	}
	if tr.Title != "La Plena" || tr.Artist != "W Sound" || tr.Genre != "Reggaeton" {
		t.Errorf("tags: %+v", tr)
	}
	// 200 frames * 1152 samples / 44100 Hz = 5.22 s
	if tr.Length != 5 || tr.BitRate != 320 || tr.SampleRate != 44100 || tr.FileType != library.FileMP3 {
		t.Errorf("stream: length=%d bitrate=%d rate=%d type=%d", tr.Length, tr.BitRate, tr.SampleRate, tr.FileType)
	}
	if tr.FileID == 0 {
		t.Error("file ID not read")
	}
}

func TestProbeMP3XingFrameCount(t *testing.T) {
	// A Xing header claiming 11500 frames: 11500*1152/44100 = 300.4 s,
	// regardless of how many bytes follow.
	tr, err := Probe(write(t, "vbr.mp3", mp3Frames(10, "Xing", 11500)))
	if err != nil {
		t.Fatal(err)
	}
	if tr.Length != 300 {
		t.Errorf("length = %d, want 300", tr.Length)
	}
	if tr.BitRate >= 320 { // VBR: average over the (tiny) file, not the nominal rate
		t.Errorf("bitrate = %d, want the VBR average", tr.BitRate)
	}
	info, err := Probe(write(t, "cbr-info.mp3", mp3Frames(10, "Info", 11500)))
	if err != nil {
		t.Fatal(err)
	}
	if info.Length != 300 || info.BitRate != 320 { // "Info" = CBR: nominal rate stays
		t.Errorf("Info header: length=%d bitrate=%d", info.Length, info.BitRate)
	}
}

func TestProbeFLAC(t *testing.T) {
	si := make([]byte, 34)
	rate, channels, depth, samples := 44100, 2, 16, uint64(44100*61)
	si[10] = byte(rate >> 12)
	si[11] = byte(rate >> 4)
	si[12] = byte(rate<<4) | byte(channels-1)<<1 | byte((depth-1)>>4)
	si[13] = byte((depth-1)&0x0f)<<4 | byte(samples>>32)
	binary.BigEndian.PutUint32(si[14:], uint32(samples))
	data := append([]byte("fLaC"), 0x80, 0, 0, 34) // last block, STREAMINFO, 34 bytes
	data = append(data, si...)
	tr, err := Probe(write(t, "track.flac", data))
	if err != nil {
		t.Fatal(err)
	}
	if tr.Length != 61 || tr.SampleRate != 44100 || tr.BitDepth != 16 || tr.BitRate != 1411 {
		t.Errorf("flac: %+v", tr)
	}
	if tr.Title != "" {
		t.Errorf("untagged file got title %q", tr.Title)
	}
}

func TestProbeWAV(t *testing.T) {
	var b bytes.Buffer
	dataLen := uint32(48000 * 2 * 3 * 8) // 8 s of 24-bit stereo at 48 kHz
	b.WriteString("RIFF")
	binary.Write(&b, binary.LittleEndian, uint32(36+dataLen))
	b.WriteString("WAVEfmt ")
	binary.Write(&b, binary.LittleEndian, struct {
		Size                      uint32
		Format, Channels          uint16
		Rate, ByteRate            uint32
		BlockAlign, BitsPerSample uint16
	}{16, 1, 2, 48000, 48000 * 2 * 3, 6, 24})
	b.WriteString("LIST")
	binary.Write(&b, binary.LittleEndian, uint32(3)) // odd chunk: padded
	b.Write([]byte{1, 2, 3, 0})
	b.WriteString("data")
	binary.Write(&b, binary.LittleEndian, dataLen)
	tr, err := Probe(write(t, "a.wav", b.Bytes()))
	if err != nil {
		t.Fatal(err)
	}
	if tr.Length != 8 || tr.SampleRate != 48000 || tr.BitDepth != 24 || tr.BitRate != 2304 {
		t.Errorf("wav: %+v", tr)
	}
}

func TestProbeAIFF(t *testing.T) {
	comm := make([]byte, 18)
	binary.BigEndian.PutUint16(comm[0:], 2)
	binary.BigEndian.PutUint32(comm[2:], 44100*10)
	binary.BigEndian.PutUint16(comm[6:], 16)
	// 44100 as an 80-bit extended float
	mant, exp := math.Frexp(44100)
	binary.BigEndian.PutUint16(comm[8:], uint16(exp-1+16383))
	binary.BigEndian.PutUint64(comm[10:], uint64(math.Ldexp(mant, 64)))
	var b bytes.Buffer
	b.WriteString("FORM")
	binary.Write(&b, binary.BigEndian, uint32(4+8+18))
	b.WriteString("AIFFCOMM")
	binary.Write(&b, binary.BigEndian, uint32(18))
	b.Write(comm)
	tr, err := Probe(write(t, "a.aiff", b.Bytes()))
	if err != nil {
		t.Fatal(err)
	}
	if tr.Length != 10 || tr.SampleRate != 44100 || tr.BitRate != 1411 || tr.FileType != library.FileAIFF {
		t.Errorf("aiff: %+v", tr)
	}
}

func TestProbeRejectsGarbage(t *testing.T) {
	if _, err := Probe(write(t, "fake.mp3", bytes.Repeat([]byte("nope"), 100))); err == nil {
		t.Error("expected an error for a file that is not audio")
	}
	if _, err := Probe(write(t, "notes.txt", []byte("x"))); err == nil {
		t.Error("expected an error for an unsupported extension")
	}
}

func TestSupported(t *testing.T) {
	for name, want := range map[string]bool{"a.MP3": true, "b.flac": true, "c.aif": true, "d.ogg": false, "e": false} {
		if Supported(name) != want {
			t.Errorf("Supported(%q) = %v", name, !want)
		}
	}
}
