package service

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/Fre0Grella/getsetmix/internal/ingestionbatch"
)

func TestRenderFilename_OmitsMissingSegments(t *testing.T) {
	got := RenderFilename(
		"{artist} - {title} ({album})",
		"https://example.test/track/1",
		"id-1",
		ingestionbatch.TrackMetadata{Title: "Title"},
	)
	if got != "Title" {
		t.Fatalf("expected filename to omit missing segments, got %q", got)
	}
}

func TestEnsureUniqueFilename_AppendsSuffix(t *testing.T) {
	dir := t.TempDir()
	original := "Artist - Title.mp3"
	path := filepath.Join(dir, original)
	if err := os.WriteFile(path, []byte("test"), 0o600); err != nil {
		t.Fatalf("failed to seed file: %v", err)
	}

	got := EnsureUniqueFilename(dir, original)
	if got != "Artist - Title-2.mp3" {
		t.Fatalf("expected suffix to be appended, got %q", got)
	}
}
