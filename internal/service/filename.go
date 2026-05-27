package service

import (
	"regexp"
	"strings"

	"github.com/Fre0Grella/getsetmix/internal/ingestionbatch"
)

var (
	illegalFilenameChars = regexp.MustCompile(`[<>:"/\\|?*\x00-\x1F]`)
	whitespaceRun        = regexp.MustCompile(`\s+`)
)

// RenderFilename builds a sanitized filename using the template tokens.
func RenderFilename(template, sourceURL, id string, md ingestionbatch.TrackMetadata) string {
	if strings.TrimSpace(template) == "" {
		return ""
	}
	replacer := strings.NewReplacer(
		"{title}", md.Title,
		"{artist}", md.Artist,
		"{album}", md.Album,
		"{genre}", md.Genre,
		"{source}", sourceURL,
		"{id}", id,
	)
	out := replacer.Replace(template)
	out = illegalFilenameChars.ReplaceAllString(out, "")
	out = whitespaceRun.ReplaceAllString(out, " ")
	out = strings.TrimSpace(out)
	out = strings.Trim(out, ".")
	return out
}
