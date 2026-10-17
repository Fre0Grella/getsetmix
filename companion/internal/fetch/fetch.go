// Package fetch downloads new tracks from the GetSetMix server into a local
// folder, one way. The server keeps its copy (it is the backup); a track
// fetched once is never fetched again, so deleting it here sticks.
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
)

// Server is where tracks come from: written by the setup when it pairs this
// computer.
type Server struct {
	URL   string `json:"url"`   // e.g. https://getsetmix.tailnet.ts.net
	Token string `json:"token"` // this computer's link token
	// Folder receives the tracks; it is also one of the watched folders.
	Folder string `json:"folder"`
}

// File is one track the server offers.
type File struct {
	Path  string `json:"path"` // library-relative, "/"-separated
	Size  int64  `json:"size"`
	MTime int64  `json:"mtime"`
}

// Listing is the server's answer to /api/link/files.
type Listing struct {
	Version string `json:"version"`
	Files   []File `json:"files"`
}

// Report says what a fetch did.
type Report struct {
	Offered    int
	Downloaded []string          // local paths
	Failed     map[string]string // server path -> reason; retried next time
	Remaining  int               // left for next time (deadline reached)
}

// ErrUnauthorized means the server no longer knows this computer.
var ErrUnauthorized = errors.New("the server doesn't recognise this computer any more: pair it again from GetSetMix Setup")

// Client talks to one server.
type Client struct {
	Server Server
	HTTP   *http.Client
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
// before, until ctx ends. state is updated in place; the caller saves it.
func (c *Client) Run(ctx context.Context, state *State, now func() time.Time) (Report, error) {
	rep := Report{Failed: map[string]string{}}
	listing, err := c.List(ctx)
	if err != nil {
		return rep, err
	}
	rep.Offered = len(listing.Files)
	for i, f := range listing.Files {
		if _, done := state.Fetched[f.Path]; done {
			continue
		}
		if ctx.Err() != nil {
			rep.Remaining = countNew(listing.Files[i:], state)
			break
		}
		dest, err := Local(c.Server.Folder, f.Path)
		if err != nil {
			rep.Failed[f.Path] = err.Error()
			continue
		}
		// Already here (copied by hand, or a first run over an old library).
		if info, err := os.Stat(dest); err == nil && info.Size() == f.Size {
			state.Fetched[f.Path] = now()
			continue
		}
		if err := c.download(ctx, f, dest); err != nil {
			if errors.Is(err, ErrUnauthorized) {
				return rep, err
			}
			if ctx.Err() != nil {
				rep.Remaining = countNew(listing.Files[i:], state)
				break
			}
			rep.Failed[f.Path] = err.Error()
			continue
		}
		state.Fetched[f.Path] = now()
		rep.Downloaded = append(rep.Downloaded, dest)
	}
	return rep, nil
}

func countNew(files []File, state *State) int {
	n := 0
	for _, f := range files {
		if _, done := state.Fetched[f.Path]; !done {
			n++
		}
	}
	return n
}

// State remembers which server tracks were fetched.
type State struct {
	Fetched map[string]time.Time `json:"fetched"`
}

const stateFile = "fetched.json"

// LoadState reads the state from dir; a missing file is an empty state.
func LoadState(dir string) (*State, error) {
	s := &State{Fetched: map[string]time.Time{}}
	data, err := os.ReadFile(filepath.Join(dir, stateFile))
	if errors.Is(err, os.ErrNotExist) {
		return s, nil
	}
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(data, s); err != nil {
		return nil, err
	}
	if s.Fetched == nil {
		s.Fetched = map[string]time.Time{}
	}
	return s, nil
}

// Save writes the state to dir.
func (s *State) Save(dir string) error {
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	tmp := filepath.Join(dir, stateFile+".tmp")
	if err := os.WriteFile(tmp, append(data, '\n'), 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, filepath.Join(dir, stateFile))
}
