package audio

// The audio id: a hash of a file's audio payload, so it survives tag edits.
//
//	a1_<32 hex>   SHA-256 of the audio payload, first 128 bits
//	f1_<32 hex>   the same over the whole file, for anything that does not parse
//
// The payload per container and the exact rules are in
// docs/design/library.md, section 4.2. The server computes the same id in
// app/audiohash.py; both are checked against the shared fixtures in
// testdata/audiohash at the repository root, so the two cannot drift apart.
// Keep this file a line-by-line match of the Python rules.

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

const (
	hashAlgorithm = "a1"
	hashFallback  = "f1"
	// mp3ScanLimit is how far past the ID3v2 tags an MP3's first frame may start.
	mp3ScanLimit = 1 << 20
)

// errNotParsed means the file does not follow its container's rule: it gets
// the fallback id.
var errNotParsed = errors.New("does not parse")

type byteRange struct{ start, end int64 }

type payloadRule func(f *hashFile) ([]byteRange, error)

// The container is chosen by the file extension, lowercased.
var payloadRules = map[string]payloadRule{
	".mp3":  mp3Payload,
	".flac": flacPayload,
	".wav":  wavPayload,
	".aif":  aiffPayload,
	".aiff": aiffPayload,
	".m4a":  mp4Payload,
	".mp4":  mp4Payload,
}

// ID returns the audio id of the file at path. A damaged file gets the
// fallback id; an error means the file could not be read at all.
func ID(path string) (string, error) {
	fh, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer fh.Close()
	info, err := fh.Stat()
	if err != nil {
		return "", err
	}
	size := info.Size()
	if rule, ok := payloadRules[strings.ToLower(filepath.Ext(path))]; ok {
		ranges, err := rule(&hashFile{r: fh, size: size})
		switch {
		case err == nil:
			for _, r := range ranges {
				if r.end > r.start {
					sum, err := digest(fh, ranges)
					if err != nil {
						return "", err
					}
					return hashAlgorithm + "_" + sum, nil
				}
			}
		case !errors.Is(err, errNotParsed):
			return "", err
		}
	}
	sum, err := digest(fh, []byteRange{{0, size}})
	if err != nil {
		return "", err
	}
	return hashFallback + "_" + sum, nil
}

// IsFallback reports whether id is a fallback id (a hash of the whole file).
func IsFallback(id string) bool {
	return strings.HasPrefix(id, hashFallback+"_")
}

func digest(r io.ReaderAt, ranges []byteRange) (string, error) {
	h := sha256.New()
	for _, rg := range ranges {
		n, err := io.Copy(h, io.NewSectionReader(r, rg.start, rg.end-rg.start))
		if err != nil {
			return "", err
		}
		if n != rg.end-rg.start {
			return "", errors.New("file shrank while it was hashed")
		}
	}
	return hex.EncodeToString(h.Sum(nil))[:32], nil
}

type hashFile struct {
	r    io.ReaderAt
	size int64
}

// read returns exactly n bytes at pos, or errNotParsed.
func (f *hashFile) read(pos, n int64) ([]byte, error) {
	if pos < 0 || n < 0 || pos+n > f.size {
		return nil, errNotParsed
	}
	buf := make([]byte, n)
	got, err := f.r.ReadAt(buf, pos)
	if int64(got) == n {
		return buf, nil
	}
	if err == nil || errors.Is(err, io.EOF) {
		return nil, errNotParsed
	}
	return nil, err
}

// ------------------------------------------------------------------ ID3v2

// skipID3v2 moves past every ID3v2 tag that starts at pos (header, size,
// optional footer).
func skipID3v2(f *hashFile, pos int64) (int64, error) {
	for pos+10 <= f.size {
		magic, err := f.read(pos, 3)
		if err != nil {
			return 0, err
		}
		if string(magic) != "ID3" {
			break
		}
		head, err := f.read(pos, 10)
		if err != nil {
			return 0, err
		}
		for _, b := range head[6:10] {
			if b&0x80 != 0 {
				return 0, errNotParsed // not a syncsafe size
			}
		}
		tag := int64(head[6])<<21 | int64(head[7])<<14 | int64(head[8])<<7 | int64(head[9])
		pos += 10 + tag
		if head[5]&0x10 != 0 {
			pos += 10
		}
		if pos > f.size {
			return 0, errNotParsed
		}
	}
	return pos, nil
}

// -------------------------------------------------------------------- MP3

var (
	mpeg1L3Rates = [15]int64{0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320}
	mpeg2L3Rates = [15]int64{0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160}
	sampleRates  = map[byte][3]int64{3: {44100, 48000, 32000}, 2: {22050, 24000, 16000}, 0: {11025, 12000, 8000}}
)

// frameLength is the length of the Layer III frame whose header is h, or 0
// if h is not one.
func frameLength(h []byte) int64 {
	if h[0] != 0xFF || h[1]&0xE0 != 0xE0 {
		return 0
	}
	version := (h[1] >> 3) & 3
	layer := (h[1] >> 1) & 3
	bitrate := h[2] >> 4
	rate := (h[2] >> 2) & 3
	if version == 1 || layer != 1 || bitrate == 0 || bitrate == 15 || rate == 3 {
		return 0
	}
	padding := int64((h[2] >> 1) & 1)
	if version == 3 {
		return 144000*mpeg1L3Rates[bitrate]/sampleRates[3][rate] + padding
	}
	return 72000*mpeg2L3Rates[bitrate]/sampleRates[version][rate] + padding
}

// sameStream reports whether b has the sync bits and a's version, layer and
// sample rate.
func sameStream(a, b []byte) bool {
	return b[0] == 0xFF && b[1]&0xE0 == 0xE0 &&
		a[1]&0x1E == b[1]&0x1E && // version and layer
		a[2]&0x0C == b[2]&0x0C // sample rate
}

func isDigits(b []byte) bool {
	if len(b) == 0 {
		return false
	}
	for _, c := range b {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}

// mp3End drops trailing ID3v1, Lyrics3v2 and APEv2 tags, in any order.
func mp3End(f *hashFile, start int64) (int64, error) {
	end := f.size
	for {
		if end-128 >= start {
			b, err := f.read(end-128, 3)
			if err != nil {
				return 0, err
			}
			if string(b) == "TAG" {
				end -= 128
				continue
			}
		}
		if end-15 >= start {
			b, err := f.read(end-9, 9)
			if err != nil {
				return 0, err
			}
			if string(b) == "LYRICS200" {
				digits, err := f.read(end-15, 6)
				if err != nil {
					return 0, err
				}
				if isDigits(digits) {
					n, _ := strconv.ParseInt(string(digits), 10, 64)
					drop := n + 15
					if end-drop < start {
						return 0, errNotParsed
					}
					end -= drop
					continue
				}
			}
		}
		if end-32 >= start {
			b, err := f.read(end-32, 8)
			if err != nil {
				return 0, err
			}
			if string(b) == "APETAGEX" {
				footer, err := f.read(end-32, 32)
				if err != nil {
					return 0, err
				}
				tag := int64(binary.LittleEndian.Uint32(footer[12:16]))
				flags := binary.LittleEndian.Uint32(footer[20:24])
				drop := tag
				if flags&0x80000000 != 0 {
					drop += 32
				}
				if drop < 32 || end-drop < start {
					return 0, errNotParsed
				}
				end -= drop
				continue
			}
		}
		return end, nil
	}
}

func mp3Payload(f *hashFile) ([]byteRange, error) {
	start, err := skipID3v2(f, 0)
	if err != nil {
		return nil, err
	}
	end, err := mp3End(f, start)
	if err != nil {
		return nil, err
	}
	limit := min(end, start+mp3ScanLimit)
	window, err := f.read(start, limit-start)
	if err != nil {
		return nil, err
	}
	for i := bytes.IndexByte(window, 0xFF); i != -1; {
		pos := start + int64(i)
		if pos+4 <= end {
			head, err := f.read(pos, 4)
			if err != nil {
				return nil, err
			}
			if length := frameLength(head); length > 0 {
				next := pos + length
				if next == end {
					return []byteRange{{pos, end}}, nil
				}
				if next+4 <= end {
					after, err := f.read(next, 4)
					if err != nil {
						return nil, err
					}
					if sameStream(head, after) {
						return []byteRange{{pos, end}}, nil
					}
				}
			}
		}
		j := bytes.IndexByte(window[i+1:], 0xFF)
		if j == -1 {
			break
		}
		i += 1 + j
	}
	return nil, errNotParsed
}

// ------------------------------------------------------------------- FLAC

func flacPayload(f *hashFile) ([]byteRange, error) {
	pos, err := skipID3v2(f, 0)
	if err != nil {
		return nil, err
	}
	magic, err := f.read(pos, 4)
	if err != nil {
		return nil, err
	}
	if string(magic) != "fLaC" {
		return nil, errNotParsed
	}
	pos += 4
	for {
		head, err := f.read(pos, 4)
		if err != nil {
			return nil, err
		}
		pos += 4 + (int64(head[1])<<16 | int64(head[2])<<8 | int64(head[3]))
		if pos > f.size {
			return nil, errNotParsed
		}
		if head[0]&0x80 != 0 {
			return []byteRange{{pos, f.size}}, nil
		}
	}
}

// ---------------------------------------------------- RIFF and IFF chunks

func chunkPayload(f *hashFile, magic string, forms []string, order binary.ByteOrder,
	first, second string) ([]byteRange, error) {
	head, err := f.read(0, 12)
	if err != nil {
		return nil, err
	}
	formOK := false
	for _, form := range forms {
		formOK = formOK || string(head[8:12]) == form
	}
	if string(head[:4]) != magic || !formOK {
		return nil, errNotParsed
	}
	found := map[string]byteRange{}
	pos := int64(12)
	for pos+8 <= f.size {
		h, err := f.read(pos, 8)
		if err != nil {
			return nil, err
		}
		kind, size := string(h[:4]), int64(order.Uint32(h[4:8]))
		start, end := pos+8, pos+8+size
		if end > f.size {
			return nil, errNotParsed
		}
		if _, have := found[kind]; !have && (kind == first || kind == second) {
			found[kind] = byteRange{start, end}
		}
		pos = end + size&1
	}
	if len(found) != 2 {
		return nil, errNotParsed
	}
	return []byteRange{found[first], found[second]}, nil
}

func wavPayload(f *hashFile) ([]byteRange, error) {
	return chunkPayload(f, "RIFF", []string{"WAVE"}, binary.LittleEndian, "fmt ", "data")
}

func aiffPayload(f *hashFile) ([]byteRange, error) {
	return chunkPayload(f, "FORM", []string{"AIFF", "AIFC"}, binary.BigEndian, "COMM", "SSND")
}

// -------------------------------------------------------------------- MP4

func mp4Payload(f *hashFile) ([]byteRange, error) {
	var mdats []byteRange
	pos := int64(0)
	for pos+8 <= f.size {
		h, err := f.read(pos, 8)
		if err != nil {
			return nil, err
		}
		size, kind := uint64(binary.BigEndian.Uint32(h[:4])), string(h[4:8])
		head := uint64(8)
		switch size {
		case 1:
			big, err := f.read(pos+8, 8)
			if err != nil {
				return nil, err
			}
			size, head = binary.BigEndian.Uint64(big), 16
		case 0:
			size = uint64(f.size - pos)
		}
		if size < head || size > uint64(f.size-pos) {
			return nil, errNotParsed
		}
		if kind == "mdat" {
			mdats = append(mdats, byteRange{pos + int64(head), pos + int64(size)})
		}
		pos += int64(size)
	}
	if len(mdats) == 0 {
		return nil, errNotParsed
	}
	return mdats, nil
}
