package ingestionbatch

import (
	"context"
	"errors"
	"testing"
)

type fakeHistory struct{}

func (f *fakeHistory) SeenSourceURL(ctx context.Context, sourceURL string) (bool, error) { return false, nil }
func (f *fakeHistory) SeenFilename(ctx context.Context, filename string) (bool, error)   { return false, nil }

type historyStub struct {
	seenURLs      map[string]bool
	seenFilenames map[string]bool
}

func (h *historyStub) SeenSourceURL(ctx context.Context, sourceURL string) (bool, error) {
	if h.seenURLs == nil {
		return false, nil
	}
	return h.seenURLs[sourceURL], nil
}

func (h *historyStub) SeenFilename(ctx context.Context, filename string) (bool, error) {
	if h.seenFilenames == nil {
		return false, nil
	}
	return h.seenFilenames[filename], nil
}

func TestIngestionBatch_CreateAndAddSourceURL(t *testing.T) {
	ctx := context.Background()
	m := NewModule(&fakeHistory{})

	batchID, err := m.CreateBatch(ctx)
	if err != nil {
		t.Fatalf("CreateBatch error: %v", err)
	}
	if batchID == "" {
		t.Fatalf("expected non-empty batchID")
	}

	trackID, err := m.AddToBatch(ctx, batchID, AddStagedTrackInput{
		SourceURL: "https://example.test/track/123",
		Metadata: TrackMetadata{Title: "Title", Artist: "Artist"},
	})
	if err != nil {
		t.Fatalf("AddToBatch error: %v", err)
	}
	if trackID == "" {
		t.Fatalf("expected non-empty trackID")
	}

	batch, err := m.GetBatch(ctx, batchID)
	if err != nil {
		t.Fatalf("GetBatch error: %v", err)
	}
	if got, want := len(batch.Tracks), 1; got != want {
		t.Fatalf("expected %d tracks, got %d", want, got)
	}
	gotTrack := batch.Tracks[0]
	if gotTrack.ID != trackID {
		t.Fatalf("expected track ID %q, got %q", trackID, gotTrack.ID)
	}
	if gotTrack.SourceURL != "https://example.test/track/123" {
		t.Fatalf("unexpected SourceURL: %q", gotTrack.SourceURL)
	}
	if gotTrack.Metadata.Title != "Title" || gotTrack.Metadata.Artist != "Artist" {
		t.Fatalf("unexpected metadata: %+v", gotTrack.Metadata)
	}
	if gotTrack.Status != StatusQueued {
		t.Fatalf("expected status %q, got %q", StatusQueued, gotTrack.Status)
	}
}

func TestIngestionBatch_EditMetadataUntilDownloadingStarts(t *testing.T) {
	ctx := context.Background()
	m := NewModule(&fakeHistory{})

	batchID, err := m.CreateBatch(ctx)
	if err != nil {
		t.Fatalf("CreateBatch error: %v", err)
	}

	trackID, err := m.AddToBatch(ctx, batchID, AddStagedTrackInput{
		SourceURL: "https://example.test/track/123",
		Metadata:  TrackMetadata{Title: "Old", Artist: "Artist"},
	})
	if err != nil {
		t.Fatalf("AddToBatch error: %v", err)
	}

	if err := m.UpdateTrackMetadata(ctx, batchID, trackID, TrackMetadata{Title: "New", Artist: "Artist"}); err != nil {
		t.Fatalf("UpdateTrackMetadata error: %v", err)
	}

	batch, err := m.GetBatch(ctx, batchID)
	if err != nil {
		t.Fatalf("GetBatch error: %v", err)
	}
	if batch.Tracks[0].Metadata.Title != "New" {
		t.Fatalf("expected title to be updated, got %q", batch.Tracks[0].Metadata.Title)
	}

	if err := m.MarkDownloading(ctx, batchID, trackID); err != nil {
		t.Fatalf("MarkDownloading error: %v", err)
	}
	if err := m.UpdateTrackMetadata(ctx, batchID, trackID, TrackMetadata{Title: "Nope", Artist: "Artist"}); err == nil {
		t.Fatalf("expected metadata edit to fail after downloading starts")
	}
}

func TestIngestionBatch_StartRunDisallowsAdd(t *testing.T) {
	ctx := context.Background()
	m := NewModule(&fakeHistory{})

	batchID, err := m.CreateBatch(ctx)
	if err != nil {
		t.Fatalf("CreateBatch error: %v", err)
	}

	if err := m.StartRun(ctx, batchID); err != nil {
		t.Fatalf("StartRun error: %v", err)
	}

	batch, err := m.GetBatch(ctx, batchID)
	if err != nil {
		t.Fatalf("GetBatch error: %v", err)
	}
	if !batch.Running {
		t.Fatalf("expected batch to be running")
	}

	_, err = m.AddToBatch(ctx, batchID, AddStagedTrackInput{SourceURL: "https://example.test/track/1", Metadata: TrackMetadata{Title: "T", Artist: "A"}})
	if !errors.Is(err, ErrBatchRunning) {
		t.Fatalf("expected ErrBatchRunning, got %v", err)
	}
}

func TestIngestionBatch_SetTrackFilenameDetectsDuplicates(t *testing.T) {
	ctx := context.Background()
	m := NewModule(&fakeHistory{})

	batchID, err := m.CreateBatch(ctx)
	if err != nil {
		t.Fatalf("CreateBatch error: %v", err)
	}

	track1, err := m.AddToBatch(ctx, batchID, AddStagedTrackInput{SourceURL: "https://example.test/track/1", Metadata: TrackMetadata{Title: "T1", Artist: "A"}})
	if err != nil {
		t.Fatalf("AddToBatch error: %v", err)
	}
	track2, err := m.AddToBatch(ctx, batchID, AddStagedTrackInput{SourceURL: "https://example.test/track/2", Metadata: TrackMetadata{Title: "T2", Artist: "A"}})
	if err != nil {
		t.Fatalf("AddToBatch error: %v", err)
	}

	if err := m.SetTrackFilename(ctx, batchID, track1, "Artist - Title.mp3"); err != nil {
		t.Fatalf("SetTrackFilename error: %v", err)
	}
	if err := m.SetTrackFilename(ctx, batchID, track2, "Artist - Title.mp3"); !errors.Is(err, ErrDuplicate) {
		t.Fatalf("expected ErrDuplicate, got %v", err)
	}

	batch, err := m.GetBatch(ctx, batchID)
	if err != nil {
		t.Fatalf("GetBatch error: %v", err)
	}
	if batch.Tracks[0].Filename != "Artist - Title.mp3" {
		t.Fatalf("expected filename to be set, got %q", batch.Tracks[0].Filename)
	}
}

func TestIngestionBatch_StatusTransitions(t *testing.T) {
	ctx := context.Background()
	m := NewModule(&fakeHistory{})

	batchID, err := m.CreateBatch(ctx)
	if err != nil {
		t.Fatalf("CreateBatch error: %v", err)
	}
	trackID, err := m.AddToBatch(ctx, batchID, AddStagedTrackInput{SourceURL: "https://example.test/track/1", Metadata: TrackMetadata{Title: "T", Artist: "A"}})
	if err != nil {
		t.Fatalf("AddToBatch error: %v", err)
	}

	if err := m.MarkDownloading(ctx, batchID, trackID); err != nil {
		t.Fatalf("MarkDownloading error: %v", err)
	}
	if err := m.MarkTagging(ctx, batchID, trackID); err != nil {
		t.Fatalf("MarkTagging error: %v", err)
	}
	if err := m.MarkIngested(ctx, batchID, trackID); err != nil {
		t.Fatalf("MarkIngested error: %v", err)
	}

	batch, err := m.GetBatch(ctx, batchID)
	if err != nil {
		t.Fatalf("GetBatch error: %v", err)
	}
	if batch.Tracks[0].Status != StatusIngested {
		t.Fatalf("expected status %q, got %q", StatusIngested, batch.Tracks[0].Status)
	}

	if err := m.MarkError(ctx, batchID, trackID, "boom"); err == nil {
		t.Fatalf("expected MarkError to fail after ingested")
	}
}

func TestIngestionBatch_RetryDoesNotUnlockMetadata(t *testing.T) {
	ctx := context.Background()
	m := NewModule(&fakeHistory{})

	batchID, err := m.CreateBatch(ctx)
	if err != nil {
		t.Fatalf("CreateBatch error: %v", err)
	}
	trackID, err := m.AddToBatch(ctx, batchID, AddStagedTrackInput{SourceURL: "https://example.test/track/1", Metadata: TrackMetadata{Title: "T", Artist: "A"}})
	if err != nil {
		t.Fatalf("AddToBatch error: %v", err)
	}

	if err := m.MarkDownloading(ctx, batchID, trackID); err != nil {
		t.Fatalf("MarkDownloading error: %v", err)
	}
	if err := m.MarkError(ctx, batchID, trackID, "network"); err != nil {
		t.Fatalf("MarkError error: %v", err)
	}
	if err := m.RetryTrack(ctx, batchID, trackID); err != nil {
		t.Fatalf("RetryTrack error: %v", err)
	}

	batch, err := m.GetBatch(ctx, batchID)
	if err != nil {
		t.Fatalf("GetBatch error: %v", err)
	}
	if batch.Tracks[0].Status != StatusQueued {
		t.Fatalf("expected status %q after retry, got %q", StatusQueued, batch.Tracks[0].Status)
	}

	if err := m.UpdateTrackMetadata(ctx, batchID, trackID, TrackMetadata{Title: "NEW", Artist: "A"}); err == nil {
		t.Fatalf("expected metadata edit to remain locked after retry")
	}
}

func TestIngestionBatch_FinishRunAllowsAdd(t *testing.T) {
	ctx := context.Background()
	m := NewModule(&fakeHistory{})

	batchID, err := m.CreateBatch(ctx)
	if err != nil {
		t.Fatalf("CreateBatch error: %v", err)
	}

	if err := m.StartRun(ctx, batchID); err != nil {
		t.Fatalf("StartRun error: %v", err)
	}
	if err := m.FinishRun(ctx, batchID); err != nil {
		t.Fatalf("FinishRun error: %v", err)
	}

	batch, err := m.GetBatch(ctx, batchID)
	if err != nil {
		t.Fatalf("GetBatch error: %v", err)
	}
	if batch.Running {
		t.Fatalf("expected batch to not be running")
	}

	_, err = m.AddToBatch(ctx, batchID, AddStagedTrackInput{SourceURL: "https://example.test/track/1", Metadata: TrackMetadata{Title: "T", Artist: "A"}})
	if err != nil {
		t.Fatalf("expected add to succeed after FinishRun, got %v", err)
	}
}

func TestIngestionBatch_HistoryDuplicateBySourceURL(t *testing.T) {
	ctx := context.Background()
	h := &historyStub{seenURLs: map[string]bool{"https://example.test/track/dupe": true}}
	m := NewModule(h)

	batchID, err := m.CreateBatch(ctx)
	if err != nil {
		t.Fatalf("CreateBatch error: %v", err)
	}

	_, err = m.AddToBatch(ctx, batchID, AddStagedTrackInput{SourceURL: "https://example.test/track/dupe", Metadata: TrackMetadata{Title: "T", Artist: "A"}})
	if !errors.Is(err, ErrDuplicate) {
		t.Fatalf("expected ErrDuplicate, got %v", err)
	}
}

func TestIngestionBatch_HistoryDuplicateByFilename(t *testing.T) {
	ctx := context.Background()
	h := &historyStub{seenFilenames: map[string]bool{"dupe.mp3": true}}
	m := NewModule(h)

	batchID, err := m.CreateBatch(ctx)
	if err != nil {
		t.Fatalf("CreateBatch error: %v", err)
	}
	trackID, err := m.AddToBatch(ctx, batchID, AddStagedTrackInput{SourceURL: "https://example.test/track/1", Metadata: TrackMetadata{Title: "T", Artist: "A"}})
	if err != nil {
		t.Fatalf("AddToBatch error: %v", err)
	}

	err = m.SetTrackFilename(ctx, batchID, trackID, "dupe.mp3")
	if !errors.Is(err, ErrDuplicate) {
		t.Fatalf("expected ErrDuplicate, got %v", err)
	}
}
