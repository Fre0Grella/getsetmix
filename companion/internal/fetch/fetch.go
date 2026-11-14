// Package fetch downloads new tracks from the GetSetMix server into a local
// folder, one way. The server keeps its copy (it is the backup); a track
// fetched once is never fetched again, so deleting it here sticks.
//
// A server that speaks link protocol 2 names each track by its audio id, so a
// track the server renames or moves is not fetched a second time. Files
// Rekordbox cannot import (Ogg, Opus) stay on the server and are not
// downloaded; the state counts them for `gsm-companion status`.
//
// A protocol 2 listing also names the tracks the server removed. Fetch only
// records the ones this computer holds (removed.go); the importer lists them
// in a playlist. With the option "Delete the local file too" the local file
// goes to the recycle bin, never further.
//
// Files land as "name.part" and are renamed when complete, which the scanner
// already ignores, so the importer never sees half a track.
package fetch

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/audio"
)

// Server is where tracks come from: written by the setup when it pairs this
// computer.
type Server struct {
	URL   string `json:"url"`   // e.g. https://getsetmix.tailnet.ts.net
	Token string `json:"token"` // this computer's link token
	// Folder receives the tracks; it is also one of the watched folders.
	Folder string `json:"folder"`
	// DeleteRemovedFiles is the option "Delete the local file too": a track
	// the server removed then goes to the system's recycle bin. Off by
	// default; the file stays.
	DeleteRemovedFiles bool `json:"delete_removed_files,omitempty"`
}

// File is one track the server offers.
type File struct {
	Path  string `json:"path"` // library-relative, "/"-separated
	Size  int64  `json:"size"`
	MTime int64  `json:"mtime"`
	// Protocol 2 (docs/design/library.md, 3.5); empty from an older server.
	ID  string `json:"id,omitempty"`  // the audio id
	Rev int64  `json:"rev,omitempty"` // change number of the last change of its bytes
}

// Removed is a tombstone in a protocol 2 listing: a track trashed in
// GetSetMix ("deleted") or that vanished from the server's disk ("missing").
type Removed struct {
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
	Protocol int       `json:"protocol,omitempty"`
	Rev      int64     `json:"rev,omitempty"`
	Files    []File    `json:"files"`
	Removed  []Removed `json:"removed,omitempty"`
}

// ByID reports whether the listing identifies tracks by audio id.
func (l Listing) ByID() bool { return l.Protocol >= 2 }

// Report says what a fetch did.
type Report struct {
	Offered    int               // tracks this computer can import
	Skipped    map[string]int    // extension -> files Rekordbox cannot import, not downloaded
	Downloaded []string          // local paths
	Failed     map[string]string // server path -> reason; retried next time
	Remaining  int               // left for next time (deadline reached)
	// Tombstones (removed.go), by server path: tracks this computer holds
	// that the server removed, ones it brought back, and local files sent
	// to the recycle bin.
	Removed  []string
	Restored []string
	Recycled []string
}

// ErrUnauthorized means the server no longer knows this computer.
var ErrUnauthorized = errors.New("the server doesn't recognise this computer any more: pair it again from GetSetMix Setup")

// Client talks to one server.
type Client struct {
	Server Server
	HTTP   *http.Client
	// Recycle sends a local file to the recycle bin (recycle.Move when nil;
	// replaced in tests).
	Recycle func(path string) error
}

func (c *Client) http() *http.Client {
	if c.HTTP != nil {
		return c.HTTP
	}
	return &http.Client{Timeout: 0} // downloads can be long; contexts bound them
}

func (c *Client) get(ctx context.Context, endpoint string, q url.Values) (*http.Response, error) {
	u := strings.TrimRight(c.Server.URL, "/") + endpoint
	if len(q) > 0 {
		u += "?" + q.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.Server.Token)
	resp, err := c.http().Do(req)
	if err != nil {
		return nil, err
	}
	switch {
	case resp.StatusCode == http.StatusUnauthorized:
		resp.Body.Close()
		return nil, ErrUnauthorized
	case resp.StatusCode != http.StatusOK:
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		resp.Body.Close()
		return nil, fmt.Errorf("%s: HTTP %d %s", endpoint, resp.StatusCode, strings.TrimSpace(string(body)))
	}
	return resp, nil
}

// List asks the server what it has.
func (c *Client) List(ctx context.Context) (Listing, error) {
	var l Listing
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	resp, err := c.get(ctx, "/api/link/files", nil)
	if err != nil {
		return l, err
	}
	defer resp.Body.Close()
	err = json.NewDecoder(resp.Body).Decode(&l)
	return l, err
}

// Local maps a server path onto this computer, refusing anything that would
// land outside the folder.
func Local(folder, serverPath string) (string, error) {
	clean := path.Clean("/" + serverPath)[1:]
	if clean == "" || clean != serverPath || strings.Contains(serverPath, "\\") {
		return "", fmt.Errorf("unsafe path %q", serverPath)
	}
	return filepath.Join(folder, filepath.FromSlash(clean)), nil
}

func (c *Client) download(ctx context.Context, f File, dest string) error {
	resp, err := c.get(ctx, "/api/link/file", url.Values{"path": {f.Path}})
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	part := dest + ".part"
	out, err := os.Create(part)
	if err != nil {
		return err
	}
	n, err := io.Copy(out, resp.Body)
	if cerr := out.Close(); err == nil {
		err = cerr
	}
	if err == nil && f.Size > 0 && n != f.Size {
		err = fmt.Errorf("got %d of %d bytes", n, f.Size)
	}
	if err != nil {
		os.Remove(part)
		return err
	}
	if f.MTime > 0 {
		t := time.Unix(f.MTime, 0)
		_ = os.Chtimes(part, t, t)
	}
	return os.Rename(part, dest)
}

// Run downloads every track the server has that this computer hasn't fetched
// before and Rekordbox can import, until ctx ends. state is updated in place;
// the caller saves it.
func (c *Client) Run(ctx context.Context, state *State, now func() time.Time) (Report, error) {
	rep := Report{Failed: map[string]string{}, Skipped: map[string]int{}}
	listing, err := c.List(ctx)
	if err != nil {
		return rep, err
	}
	state.Begin(listing, c.Server.Folder)
	c.tombstones(listing, state, now(), &rep)
	var todo []File
	for _, f := range listing.Files {
		// The server keeps listing what Rekordbox cannot import, so its Library
		// view stays complete; downloading it would only fill the disk (#31).
		if !audio.Supported(f.Path) {
			rep.Skipped[strings.ToLower(path.Ext(f.Path))]++
			continue
		}
		rep.Offered++
		if !state.Has(f) {
			todo = append(todo, f)
		}
	}
	state.Skipped = rep.Skipped
	for i, f := range todo {
		if ctx.Err() != nil {
			rep.Remaining = len(todo) - i
			break
		}
		if state.Has(f) {
			continue
		}
		dest, err := Local(c.Server.Folder, f.Path)
		if err != nil {
			rep.Failed[f.Path] = err.Error()
			continue
		}
		// Already here (copied by hand, or a first run over an old library).
		if sizeIs(dest, f.Size) {
			state.Record(f, now())
			continue
		}
		if err := c.download(ctx, f, dest); err != nil {
			if errors.Is(err, ErrUnauthorized) {
				return rep, err
			}
			if ctx.Err() != nil {
				rep.Remaining = len(todo) - i
				break
			}
			rep.Failed[f.Path] = err.Error()
			continue
		}
		state.Record(f, now())
		rep.Downloaded = append(rep.Downloaded, dest)
	}
	return rep, nil
}

func sizeIs(file string, size int64) bool {
	info, err := os.Stat(file)
	return err == nil && info.Mode().IsRegular() && info.Size() == size
}
