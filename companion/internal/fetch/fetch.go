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
	"github.com/Fre0Grella/getsetmix/companion/internal/track"
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

// The listing types live in track (docs/design/library.md, 4.6.1); these
// names stay while callers move.
type (
	File    = track.File      // one track the server offers
	Removed = track.Tombstone // a tombstone in a protocol 2 listing
	Listing = track.Listing   // the server's answer to /api/link/files
)

// Report says what a fetch did.
type Report struct {
	Offered    int               // tracks this computer can import
	Skipped    map[string]int    // extension -> files Rekordbox cannot import, not downloaded
	Downloaded []string          // local paths
	Updated    []string          // local paths replaced by a newer copy (changed on the server)
	Kept       []string          // server paths changed on the server but deleted here: left alone
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

// Local maps a server path onto this computer: track.Local.
func Local(folder, serverPath string) (string, error) {
	return track.Local(folder, serverPath)
}

// download fetches f into dest through dest.part. With checkID, the audio id
// of the download must be f's before it replaces anything.
func (c *Client) download(ctx context.Context, f File, dest string, checkID bool) error {
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
	if err == nil && checkID && f.ID != "" {
		var got string
		if got, err = audio.IDAs(part, dest); err == nil && got != f.ID {
			err = fmt.Errorf("the download's audio id is %s, not %s", got, f.ID)
		}
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
		if !state.Has(f) || state.Newer(f) {
			todo = append(todo, f)
		}
	}
	state.Skipped = rep.Skipped
	for i, f := range todo {
		if ctx.Err() != nil {
			rep.Remaining = len(todo) - i
			break
		}
		var err error
		if state.Has(f) {
			if !state.Newer(f) {
				continue
			}
			err = c.refresh(ctx, f, state, now, &rep)
		} else {
			err = c.fetchNew(ctx, f, state, now, &rep)
		}
		if err == nil {
			continue
		}
		if errors.Is(err, ErrUnauthorized) {
			return rep, err
		}
		if ctx.Err() != nil {
			rep.Remaining = len(todo) - i
			break
		}
		rep.Failed[f.Path] = err.Error()
	}
	return rep, nil
}

// fetchNew downloads a track this computer has not fetched before.
func (c *Client) fetchNew(ctx context.Context, f File, state *State, now func() time.Time, rep *Report) error {
	dest, err := Local(c.Server.Folder, f.Path)
	if err != nil {
		return err
	}
	// Already here (copied by hand, or a first run over an old library).
	if !sizeIs(dest, f.Size) {
		if err := c.download(ctx, f, dest, false); err != nil {
			return err
		}
		rep.Downloaded = append(rep.Downloaded, dest)
	}
	state.Record(f, now())
	if tags, err := audio.ReadTags(dest); err == nil && f.ID != "" {
		state.Remember(f.ID, tags)
	}
	return nil
}

// refresh replaces the local copy of a track that changed on the server
// (docs/design/library.md, 4.6). A track deleted here is not fetched again:
// its new rev is recorded and nothing else happens. Otherwise the newer copy
// is downloaded, checked against the audio id, and renamed over the local
// file; the tags this computer saw before stay in the state, so the importer
// can tell which fields changed on the server.
func (c *Client) refresh(ctx context.Context, f File, state *State, now func() time.Time, rep *Report) error {
	held := state.Tracks[f.ID]
	dest, err := Local(c.Server.Folder, held.Path)
	if err != nil {
		return err
	}
	if info, err := os.Stat(dest); err != nil || !info.Mode().IsRegular() {
		held.Rev = f.Rev
		state.Tracks[f.ID] = held
		rep.Kept = append(rep.Kept, f.Path)
		return nil
	}
	if held.Tags == nil && !held.Pending {
		// Fetched before tags were remembered: the copy here is what was
		// imported, so its tags are the ones to compare with. Not when a newer
		// copy is already waiting: Rekordbox has not seen that one.
		if tags, err := audio.ReadTags(dest); err == nil {
			held.Tags = &tags
		}
	}
	if err := c.download(ctx, f, dest, true); err != nil {
		return err
	}
	held.Rev, held.At, held.Pending = f.Rev, now(), true
	state.Tracks[f.ID] = held
	rep.Updated = append(rep.Updated, dest)
	return nil
}

func sizeIs(file string, size int64) bool {
	info, err := os.Stat(file)
	return err == nil && info.Mode().IsRegular() && info.Size() == size
}
