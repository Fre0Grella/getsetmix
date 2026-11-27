// Package fetch downloads new tracks from the GetSetMix server into a local
// folder, one way. The server keeps its copy (it is the backup); a track
// fetched once is never fetched again, so deleting it here sticks.
//
// A server that speaks link protocol 2 names each track by its audio id, so a
// track the server renames or moves is not fetched a second time. Files
// Rekordbox cannot import (Ogg, Opus) stay on the server and are not
// downloaded; the state counts them for `gsm-companion status`.
//
// A protocol 2 listing also names the tracks the server removed. Only the
// ones this computer holds are recorded (removed.go); the importer lists them
// in a playlist. With the option "Delete the local file too" the local file
// goes to the recycle bin, never further.
//
// What to do with a listing is the ledger's to say (ledger.Fetched.Plan), and
// what this computer holds is the ledger's to remember (fetched.json). Fetch
// does the network and file work and records each outcome.
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
	"path/filepath"
	"strings"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/audio"
	"github.com/Fre0Grella/getsetmix/companion/internal/config"
	"github.com/Fre0Grella/getsetmix/companion/internal/ledger"
	"github.com/Fre0Grella/getsetmix/companion/internal/track"
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
	Server config.Server
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
func (c *Client) List(ctx context.Context) (track.Listing, error) {
	var l track.Listing
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

// download fetches f into dest through dest.part. With checkID, the audio id
// of the download must be f's before it replaces anything.
func (c *Client) download(ctx context.Context, f track.File, dest string, checkID bool) error {
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
// before and Rekordbox can import, until ctx ends. It asks the ledger what
// to do with the listing (ledger.Fetched.Plan), does the network and file
// work, and records each outcome. state is updated in place; the caller
// saves it.
func (c *Client) Run(ctx context.Context, state *ledger.Fetched, now func() time.Time) (Report, error) {
	rep := Report{Failed: map[string]string{}}
	listing, err := c.List(ctx)
	if err != nil {
		return rep, err
	}
	plan := state.Plan(listing, c.Server.Folder, audio.Supported, c.Server.DeleteRemovedFiles, now())
	rep.Offered, rep.Skipped = plan.Offered, plan.Skipped
	c.tombstones(plan, state, &rep)
	for i, step := range plan.Steps {
		if ctx.Err() != nil {
			rep.Remaining = len(plan.Steps) - i
			break
		}
		err := step.Err
		if err == nil {
			err = c.do(ctx, step, state, now, &rep)
		}
		if err == nil {
			continue
		}
		if errors.Is(err, ErrUnauthorized) {
			return rep, err
		}
		if ctx.Err() != nil {
			rep.Remaining = len(plan.Steps) - i
			break
		}
		rep.Failed[step.File.Path] = err.Error()
	}
	return rep, nil
}

// do carries out one step of the plan.
//
// Get: a track this computer has not fetched before, downloaded unless a
// file of its size is in place already (copied by hand, or a first run over
// an old library). Refresh: a track that changed on the server
// (docs/design/library.md, 4.6); the newer copy is downloaded, checked
// against the audio id, and renamed over the local file, and the tags this
// computer saw before stay in the state, so the importer can tell which
// fields changed on the server. Keep: a newer copy of a track deleted here,
// which is not fetched again.
func (c *Client) do(ctx context.Context, step ledger.Step, state *ledger.Fetched, now func() time.Time,
	rep *Report) error {
	f, dest := step.File, step.Dest
	switch step.Kind {
	case ledger.Keep:
		state.Kept(f)
		rep.Kept = append(rep.Kept, f.Path)
	case ledger.Refresh:
		var was *track.Tags
		if step.NeedTags {
			if tags, err := audio.ReadTags(dest); err == nil {
				was = &tags
			}
		}
		if err := c.download(ctx, f, dest, true); err != nil {
			return err
		}
		state.Refreshed(f, now(), was)
		rep.Updated = append(rep.Updated, dest)
	default:
		if !track.HasSize(dest, f.Size) {
			if err := c.download(ctx, f, dest, false); err != nil {
				return err
			}
			rep.Downloaded = append(rep.Downloaded, dest)
		}
		var tags *track.Tags
		if t, err := audio.ReadTags(dest); err == nil {
			tags = &t
		}
		state.Got(f, now(), tags)
	}
	return nil
}
