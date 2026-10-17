package library

import (
	"bytes"
	"fmt"
	"os"
	"regexp"
	"strconv"
)

// Rekordbox mirrors every playlist into masterPlaylists6.xml next to
// master.db (Id and ParentId in hex, Timestamp = updated_at in epoch ms) and
// expects the two to agree. The file is edited textually so that everything
// we don't touch stays byte-for-byte what Rekordbox wrote.

var playlistsClose = regexp.MustCompile(`(?m)^([ \t]*)</PLAYLISTS>`)

// SyncPlaylistXML records pl in the masterPlaylists6.xml at path: adds its
// NODE when the playlist was just created, refreshes its Timestamp otherwise.
// A missing file is not an error — older libraries don't have one.
func SyncPlaylistXML(path string, pl Playlist) error {
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	out, err := updatePlaylistXML(data, pl)
	if err != nil {
		return err
	}
	if bytes.Equal(out, data) {
		return nil
	}
	tmp := path + ".gsm-tmp"
	if err := os.WriteFile(tmp, out, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func updatePlaylistXML(data []byte, pl Playlist) ([]byte, error) {
	id, err := strconv.ParseUint(pl.ID, 10, 64)
	if err != nil {
		return nil, fmt.Errorf("playlist id %q: %w", pl.ID, err)
	}
	hexID := strconv.FormatUint(id, 16)
	ts := strconv.FormatInt(pl.UpdatedAt.UnixMilli(), 10)

	node := regexp.MustCompile(`<NODE Id="(?i:` + hexID + `)"[^>]*>`)
	if loc := node.FindIndex(data); loc != nil {
		stampRe := regexp.MustCompile(`Timestamp="\d*"`)
		updated := stampRe.ReplaceAll(data[loc[0]:loc[1]], []byte(`Timestamp="`+ts+`"`))
		return append(append(append([]byte{}, data[:loc[0]]...), updated...), data[loc[1]:]...), nil
	}

	m := playlistsClose.FindSubmatchIndex(data)
	if m == nil {
		return nil, fmt.Errorf("no </PLAYLISTS> element")
	}
	indent := string(data[m[2]:m[3]])
	eol := "\n"
	if bytes.Contains(data, []byte("\r\n")) {
		eol = "\r\n"
	}
	line := fmt.Sprintf(`%s  <NODE Id="%s" ParentId="0" Attribute="0" Timestamp="%s" Lib_Type="0" CheckType="0"/>%s`,
		indent, hexUpper(hexID), ts, eol)
	return append(append(append([]byte{}, data[:m[0]]...), line...), data[m[0]:]...), nil
}

func hexUpper(h string) string {
	return string(bytes.ToUpper([]byte(h)))
}
