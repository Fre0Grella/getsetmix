package tagger

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/bogem/id3v2/v2"
)

// Metadata contains the tag fields written into downloaded audio files.
type Metadata struct {
	Title  string
	Artist string
	Album  string
	Genre  string
}

// Tagger writes metadata and optional cover art into an audio file.
type Tagger interface {
	Tag(ctx context.Context, audioPath string, metadata Metadata, sourceURL, coverPath string) error
}

// ID3Tagger writes ID3v2 tags for MP3 files.
type ID3Tagger struct{}

func NewID3Tagger() *ID3Tagger {
	return &ID3Tagger{}
}

func (t *ID3Tagger) Tag(ctx context.Context, audioPath string, metadata Metadata, sourceURL, coverPath string) error {
	if strings.TrimSpace(audioPath) == "" {
		return errors.New("audio path is required")
	}
	ext := strings.ToLower(filepath.Ext(audioPath))
	if ext != ".mp3" {
		return fmt.Errorf("unsupported audio format: %s", ext)
	}

	tag, err := id3v2.Open(audioPath, id3v2.Options{Parse: true})
	if err != nil {
		return err
	}
	defer tag.Close()

	tag.SetTitle(metadata.Title)
	tag.SetArtist(metadata.Artist)
	if strings.TrimSpace(metadata.Album) != "" {
		tag.SetAlbum(metadata.Album)
	}
	if strings.TrimSpace(metadata.Genre) != "" {
		tag.SetGenre(metadata.Genre)
	}
	if strings.TrimSpace(sourceURL) != "" {
		tag.AddCommentFrame(id3v2.CommentFrame{
			Encoding:    id3v2.EncodingUTF8,
			Language:    "eng",
			Description: "Source URL",
			Text:        sourceURL,
		})
	}

	if strings.TrimSpace(coverPath) != "" {
		coverBytes, err := os.ReadFile(coverPath)
		if err != nil {
			return err
		}
		mimeType := http.DetectContentType(coverBytes)
		tag.AddAttachedPicture(id3v2.PictureFrame{
			Encoding:    id3v2.EncodingUTF8,
			MimeType:    mimeType,
			PictureType: id3v2.PTFrontCover,
			Description: "Cover",
			Picture:     coverBytes,
		})
	}

	return tag.Save()
}
