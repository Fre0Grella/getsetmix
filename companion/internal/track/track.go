// Package track holds what every part of the companion means by a track:
// the import candidate, its six tag fields, the key a path is compared by,
// and the server's listing of tracks (docs/design/library.md, 4.6.1).
//
// It is pure: it imports nothing else from the companion and no database
// driver, so the packages that only read files or talk to the server build
// and test without SQLCipher.
package track

// FileType codes of djmdContent.FileType.
const (
	FileMP3  = 1
	FileM4A  = 4
	FileFLAC = 5
	FileALAC = 6
	FileWAV  = 11
	FileAIFF = 12
)

// Track is one audio file to add to the collection.
type Track struct {
	Path    string // absolute path on this machine
	Title   string
	Artist  string
	Album   string
	Genre   string
	Comment string
	Year    int
	TrackNo int

	FileType   int
	FileSize   int64
	FileID     uint64 // filesystem identity: NTFS file ID / inode, as Rekordbox stores it
	Length     int    // seconds
	BitRate    int    // kbps
	BitDepth   int
	SampleRate int
}
