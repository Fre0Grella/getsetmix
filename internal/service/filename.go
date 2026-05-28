package service

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/Fre0Grella/getsetmix/internal/ingestionbatch"
)

var (
	illegalFilenameChars = regexp.MustCompile(`[<>:"/\\|?*\x00-\x1F]`)
	whitespaceRun        = regexp.MustCompile(`\s+`)
	filenameTokens       = regexp.MustCompile(`\{(title|artist|album|genre|source|id)\}`)
)

type filenamePart struct {
	text    string
	token   string
	isToken bool
}

// RenderFilename builds a sanitized filename using the template tokens,
// omitting missing token segments without leaving stray separators.
func RenderFilename(template, sourceURL, id string, md ingestionbatch.TrackMetadata) string {
	if strings.TrimSpace(template) == "" {
		return ""
	}

	parts := splitFilenameTemplate(template)
	var builder strings.Builder
	for i, part := range parts {
		if part.isToken {
			builder.WriteString(tokenValue(part.token, sourceURL, id, md))
			continue
		}
		if shouldKeepText(parts, i, sourceURL, id, md) {
			builder.WriteString(part.text)
		}
	}

	out := builder.String()
	out = illegalFilenameChars.ReplaceAllString(out, "")
	out = whitespaceRun.ReplaceAllString(out, " ")
	out = strings.TrimSpace(out)
	out = strings.Trim(out, ".")
	return out
}

func splitFilenameTemplate(template string) []filenamePart {
	matches := filenameTokens.FindAllStringSubmatchIndex(template, -1)
	if len(matches) == 0 {
		return []filenamePart{{text: template}}
	}

	parts := make([]filenamePart, 0, len(matches)*2+1)
	last := 0
	for _, match := range matches {
		start := match[0]
		end := match[1]
		tokenStart := match[2]
		tokenEnd := match[3]

		if start > last {
			parts = append(parts, filenamePart{text: template[last:start]})
		}
		parts = append(parts, filenamePart{
			token:   template[tokenStart:tokenEnd],
			isToken: true,
		})
		last = end
	}
	if last < len(template) {
		parts = append(parts, filenamePart{text: template[last:]})
	}
	return parts
}

func shouldKeepText(parts []filenamePart, index int, sourceURL, id string, md ingestionbatch.TrackMetadata) bool {
	prevTokenValue := ""
	nextTokenValue := ""
	prevFound := false
	nextFound := false

	for i := index - 1; i >= 0; i-- {
		if parts[i].isToken {
			prevFound = true
			prevTokenValue = tokenValue(parts[i].token, sourceURL, id, md)
			break
		}
	}
	for i := index + 1; i < len(parts); i++ {
		if parts[i].isToken {
			nextFound = true
			nextTokenValue = tokenValue(parts[i].token, sourceURL, id, md)
			break
		}
	}

	if !prevFound && !nextFound {
		return true
	}
	if !prevFound {
		return nextTokenValue != ""
	}
	if !nextFound {
		return prevTokenValue != ""
	}
	return prevTokenValue != "" && nextTokenValue != ""
}

func tokenValue(token, sourceURL, id string, md ingestionbatch.TrackMetadata) string {
	switch token {
	case "title":
		return strings.TrimSpace(md.Title)
	case "artist":
		return strings.TrimSpace(md.Artist)
	case "album":
		return strings.TrimSpace(md.Album)
	case "genre":
		return strings.TrimSpace(md.Genre)
	case "source":
		return strings.TrimSpace(sourceURL)
	case "id":
		return strings.TrimSpace(id)
	default:
		return ""
	}
}

// EnsureUniqueFilename adds a numeric suffix if the filename already exists on disk.
func EnsureUniqueFilename(outputDir, filename string) string {
	if strings.TrimSpace(outputDir) == "" || strings.TrimSpace(filename) == "" {
		return filename
	}
	if !pathExists(filepath.Join(outputDir, filename)) {
		return filename
	}

	ext := filepath.Ext(filename)
	base := strings.TrimSuffix(filename, ext)
	for i := 2; ; i++ {
		candidate := fmt.Sprintf("%s-%d%s", base, i, ext)
		if !pathExists(filepath.Join(outputDir, candidate)) {
			return candidate
		}
	}
}

func pathExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
