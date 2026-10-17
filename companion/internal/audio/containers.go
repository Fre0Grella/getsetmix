package audio

import (
	"bytes"
	"encoding/binary"
	"errors"
	"io"
	"math"
)

var errFormat = errors.New("unrecognised stream header")

// ------------------------------------------------------------------ MP3

var (
	mp3Bitrates = [2][16]int{ // [MPEG-1, MPEG-2/2.5] Layer III, kbps
		{0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0},
		{0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0},
	}
	mp3Rates = [4][3]int{ // [version bits][rate index]
		{11025, 12000, 8000},  // MPEG 2.5
		{0, 0, 0},             // reserved
		{22050, 24000, 16000}, // MPEG 2
		{44100, 48000, 32000}, // MPEG 1
	}
)

// probeMP3 reads the first Layer III frame after any ID3v2 tag. VBR files
// carry a Xing/Info or VBRI header there with the frame count; otherwise the
// stream is CBR and the duration follows from its size.
func probeMP3(r io.ReadSeeker, size int64) (stream, error) {
	var start int64
	hdr := make([]byte, 10)
	if _, err := io.ReadFull(r, hdr); err != nil {
		return stream{}, err
	}
	if string(hdr[:3]) == "ID3" {
		start = 10 + int64(hdr[6]&0x7f)<<21 | int64(hdr[7]&0x7f)<<14 | int64(hdr[8]&0x7f)<<7 | int64(hdr[9]&0x7f)
		if hdr[5]&0x10 != 0 { // footer present
			start += 10
		}
	}
	buf := make([]byte, 64*1024)
	if _, err := r.Seek(start, io.SeekStart); err != nil {
		return stream{}, err
	}
	n, _ := io.ReadFull(r, buf)
	buf = buf[:n]

	for i := 0; i+4 <= len(buf); i++ {
		if buf[i] != 0xff || buf[i+1]&0xe0 != 0xe0 {
			continue
		}
		version := (buf[i+1] >> 3) & 3
		layer := (buf[i+1] >> 1) & 3
		brIdx := buf[i+2] >> 4
		srIdx := (buf[i+2] >> 2) & 3
		if version == 1 || layer != 1 || brIdx == 0 || brIdx == 15 || srIdx == 3 {
			continue // not a Layer III frame header
		}
		mpeg1 := version == 3
		table := 1
		if mpeg1 {
			table = 0
		}
		kbps := mp3Bitrates[table][brIdx]
		rate := mp3Rates[version][srIdx]
		mono := buf[i+3]>>6 == 3
		samplesPerFrame := 576
		if mpeg1 {
			samplesPerFrame = 1152
		}
		s := stream{bitRate: kbps, sampleRate: rate, bitDepth: 16}

		// Side-info length decides where Xing/Info sits.
		side := 32
		switch {
		case mpeg1 && mono:
			side = 17
		case !mpeg1 && mono:
			side = 9
		case !mpeg1:
			side = 17
		}
		if frames, vbr := frameCount(buf, i, side); frames > 0 {
			s.seconds = float64(frames) * float64(samplesPerFrame) / float64(rate)
			if vbr { // report the average rate, as Rekordbox does
				s.bitRate = int(math.Round(float64(size-start-int64(i)) * 8 / s.seconds / 1000))
			}
		} else {
			audioBytes := size - start - int64(i)
			if hasID3v1(r, size) {
				audioBytes -= 128
			}
			s.seconds = float64(audioBytes) * 8 / float64(kbps*1000)
		}
		return s, nil
	}
	return stream{}, errFormat
}

// frameCount reads the frame total from a Xing/Info header (after the side
// info) or a VBRI header (32 bytes in). "Info" is the CBR flavour of Xing.
func frameCount(buf []byte, frame, side int) (frames uint32, vbr bool) {
	if at := frame + 4 + side; at+12 <= len(buf) {
		switch string(buf[at : at+4]) {
		case "Xing", "Info":
			if binary.BigEndian.Uint32(buf[at+4:])&1 == 0 { // frames field absent
				return 0, false
			}
			return binary.BigEndian.Uint32(buf[at+8:]), string(buf[at:at+4]) == "Xing"
		}
	}
	if at := frame + 4 + 32; at+18 <= len(buf) && string(buf[at:at+4]) == "VBRI" {
		return binary.BigEndian.Uint32(buf[at+14:]), true
	}
	return 0, false
}

func hasID3v1(r io.ReadSeeker, size int64) bool {
	if size < 128 {
		return false
	}
	tag := make([]byte, 3)
	if _, err := r.Seek(size-128, io.SeekStart); err != nil {
		return false
	}
	_, err := io.ReadFull(r, tag)
	return err == nil && string(tag) == "TAG"
}

// ----------------------------------------------------------------- FLAC

// probeFLAC reads STREAMINFO, which is always the first metadata block.
func probeFLAC(r io.Reader) (stream, error) {
	b := make([]byte, 4+4+34)
	if _, err := io.ReadFull(r, b); err != nil {
		return stream{}, err
	}
	if string(b[:4]) != "fLaC" || b[4]&0x7f != 0 {
		return stream{}, errFormat
	}
	si := b[8:]
	rate := int(si[10])<<12 | int(si[11])<<4 | int(si[12])>>4
	channels := int(si[12]>>1&7) + 1
	depth := int(si[12]&1)<<4 | int(si[13]>>4) + 1
	samples := uint64(si[13]&0x0f)<<32 | uint64(binary.BigEndian.Uint32(si[14:18]))
	if rate == 0 {
		return stream{}, errFormat
	}
	s := stream{sampleRate: rate, bitDepth: depth, seconds: float64(samples) / float64(rate)}
	// Rekordbox lists lossless files at their PCM rate (1411 kbps for CD audio).
	s.bitRate = rate * depth * channels / 1000
	return s, nil
}

// ------------------------------------------------------------------ WAV

func probeWAV(r io.Reader) (stream, error) {
	head := make([]byte, 12)
	if _, err := io.ReadFull(r, head); err != nil {
		return stream{}, err
	}
	if string(head[:4]) != "RIFF" || string(head[8:12]) != "WAVE" {
		return stream{}, errFormat
	}
	var s stream
	var byteRate uint32
	for {
		ch := make([]byte, 8)
		if _, err := io.ReadFull(r, ch); err != nil {
			return s, err
		}
		id, n := string(ch[:4]), binary.LittleEndian.Uint32(ch[4:])
		switch id {
		case "fmt ":
			f := make([]byte, n)
			if _, err := io.ReadFull(r, f); err != nil || n < 16 {
				return s, errFormat
			}
			channels := int(binary.LittleEndian.Uint16(f[2:]))
			s.sampleRate = int(binary.LittleEndian.Uint32(f[4:]))
			byteRate = binary.LittleEndian.Uint32(f[8:])
			s.bitDepth = int(binary.LittleEndian.Uint16(f[14:]))
			s.bitRate = s.sampleRate * s.bitDepth * channels / 1000
			if n%2 == 1 {
				_, _ = io.CopyN(io.Discard, r, 1)
			}
		case "data":
			if byteRate == 0 {
				return s, errFormat
			}
			s.seconds = float64(n) / float64(byteRate)
			return s, nil
		default:
			if _, err := io.CopyN(io.Discard, r, int64(n)+int64(n%2)); err != nil {
				return s, err
			}
		}
	}
}

// ----------------------------------------------------------------- AIFF

func probeAIFF(r io.Reader) (stream, error) {
	head := make([]byte, 12)
	if _, err := io.ReadFull(r, head); err != nil {
		return stream{}, err
	}
	if string(head[:4]) != "FORM" || (string(head[8:12]) != "AIFF" && string(head[8:12]) != "AIFC") {
		return stream{}, errFormat
	}
	for {
		ch := make([]byte, 8)
		if _, err := io.ReadFull(r, ch); err != nil {
			return stream{}, err
		}
		id, n := string(ch[:4]), binary.BigEndian.Uint32(ch[4:])
		if id != "COMM" {
			if _, err := io.CopyN(io.Discard, r, int64(n)+int64(n%2)); err != nil {
				return stream{}, err
			}
			continue
		}
		c := make([]byte, n)
		if _, err := io.ReadFull(r, c); err != nil || n < 18 {
			return stream{}, errFormat
		}
		channels := int(binary.BigEndian.Uint16(c[0:]))
		frames := binary.BigEndian.Uint32(c[2:])
		depth := int(binary.BigEndian.Uint16(c[6:]))
		rate := int(extended80(c[8:18]))
		if rate == 0 {
			return stream{}, errFormat
		}
		return stream{
			sampleRate: rate, bitDepth: depth,
			seconds: float64(frames) / float64(rate),
			bitRate: rate * depth * channels / 1000,
		}, nil
	}
}

// extended80 decodes the 80-bit IEEE 754 extended float AIFF uses for rates.
func extended80(b []byte) float64 {
	exp := int(binary.BigEndian.Uint16(b[0:2]) & 0x7fff)
	mant := binary.BigEndian.Uint64(b[2:10])
	if exp == 0 && mant == 0 {
		return 0
	}
	return float64(mant) * math.Pow(2, float64(exp-16383-63))
}

// ------------------------------------------------------------------ MP4

// probeMP4 walks the atom tree for the movie header (duration) and the
// sample description (sample rate, ALAC vs AAC).
func probeMP4(r io.ReadSeeker, size int64) (stream, error) {
	var s stream
	var timescale, duration uint64
	var walk func(end int64) error
	walk = func(end int64) error {
		for {
			pos, err := r.Seek(0, io.SeekCurrent)
			if err != nil || pos+8 > end {
				return err
			}
			h := make([]byte, 8)
			if _, err := io.ReadFull(r, h); err != nil {
				return err
			}
			n := int64(binary.BigEndian.Uint32(h[:4]))
			kind := string(h[4:8])
			hdr := int64(8)
			if n == 1 {
				ext := make([]byte, 8)
				if _, err := io.ReadFull(r, ext); err != nil {
					return err
				}
				n, hdr = int64(binary.BigEndian.Uint64(ext)), 16
			} else if n == 0 {
				n = end - pos
			}
			if n < hdr {
				return errFormat
			}
			switch kind {
			case "moov", "trak", "mdia", "minf", "stbl":
				if err := walk(pos + n); err != nil {
					return err
				}
			case "mvhd":
				b := make([]byte, min(n-hdr, 32))
				if _, err := io.ReadFull(r, b); err != nil {
					return err
				}
				if b[0] == 1 && len(b) >= 32 {
					timescale = uint64(binary.BigEndian.Uint32(b[20:]))
					duration = binary.BigEndian.Uint64(b[24:])
				} else if len(b) >= 20 {
					timescale = uint64(binary.BigEndian.Uint32(b[12:]))
					duration = uint64(binary.BigEndian.Uint32(b[16:]))
				}
			case "stsd":
				b := make([]byte, min(n-hdr, 64))
				if _, err := io.ReadFull(r, b); err != nil {
					return err
				}
				// version/flags(4) count(4) then the first sample entry:
				// size(4) format(4) reserved(6) dref(2) ... rate at +32 (16.16)
				if len(b) >= 8+36 {
					entry := b[8:]
					s.alac = bytes.Equal(entry[4:8], []byte("alac"))
					s.bitDepth = int(binary.BigEndian.Uint16(entry[26:28]))
					s.sampleRate = int(binary.BigEndian.Uint32(entry[32:36]) >> 16)
				}
			}
			if _, err := r.Seek(pos+n, io.SeekStart); err != nil {
				return err
			}
		}
	}
	if err := walk(size); err != nil && !errors.Is(err, io.EOF) {
		return s, err
	}
	if timescale == 0 || duration == 0 {
		return s, errFormat
	}
	s.seconds = float64(duration) / float64(timescale)
	s.bitRate = int(math.Round(float64(size) * 8 / s.seconds / 1000))
	if !s.alac {
		s.bitDepth = 16
	}
	return s, nil
}
