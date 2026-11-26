package track

// File is one track the server offers.
type File struct {
	Path  string `json:"path"` // library-relative, "/"-separated
	Size  int64  `json:"size"`
	MTime int64  `json:"mtime"`
	// Protocol 2 (docs/design/library.md, 3.5); empty from an older server.
	ID  string `json:"id,omitempty"`  // the audio id
	Rev int64  `json:"rev,omitempty"` // change number of the last change of its bytes
}

// Tombstone is the server saying a track is removed, as a protocol 2
// listing names it: trashed in GetSetMix ("deleted") or vanished from the
// server's disk ("missing").
type Tombstone struct {
	ID     string `json:"id"`
	Path   string `json:"path"`
	At     string `json:"at"`
	Reason string `json:"reason"`
}

// Listing is the server's answer to /api/link/files.
type Listing struct {
	Version string `json:"version"`
	// Protocol is 2 or more from a server that lists audio ids; an older
	// server leaves it out (protocol 1), and tracks are then known by path.
	Protocol int         `json:"protocol,omitempty"`
	Rev      int64       `json:"rev,omitempty"`
	Files    []File      `json:"files"`
	Removed  []Tombstone `json:"removed,omitempty"`
}

// ByID reports whether the listing identifies tracks by audio id.
func (l Listing) ByID() bool { return l.Protocol >= 2 }
