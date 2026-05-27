package orchestrator

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/internal/adapterbus"
	"github.com/Fre0Grella/getsetmix/internal/ingestionbatch"
)

type fakeAdapter struct {
	downloadErr error
}

func (f fakeAdapter) Preview(ctx context.Context, req adapterbus.PreviewRequest) (adapterbus.PreviewResponse, error) {
	return adapterbus.PreviewResponse{}, errors.New("not implemented")
}

func (f fakeAdapter) Download(ctx context.Context, req adapterbus.DownloadRequest) (adapterbus.DownloadResponse, error) {
	if f.downloadErr != nil {
		return adapterbus.DownloadResponse{}, f.downloadErr
	}
	return adapterbus.DownloadResponse{AudioPath: "/tmp/audio.mp3"}, nil
}

type noopHistory struct{}

func (noopHistory) Record(ctx context.Context, sourceURL, filename string) error { return nil }

func TestOrchestratorCompletesBatch(t *testing.T) {
	module := ingestionbatch.NewModule(nil)
	batchID, err := module.CreateBatch(context.Background())
	if err != nil {
		t.Fatalf("create batch: %v", err)
	}
	trackID, err := module.AddToBatch(context.Background(), batchID, ingestionbatch.AddStagedTrackInput{
		SourceURL: "https://example.com",
		Metadata: ingestionbatch.TrackMetadata{
			Title:  "Track",
			Artist: "Artist",
		},
	})
	if err != nil {
		t.Fatalf("add track: %v", err)
	}
	if err := module.StartRun(context.Background(), batchID); err != nil {
		t.Fatalf("start run: %v", err)
	}

	orch := New(fakeAdapter{}, module, noopHistory{}, "mp3-320", 1)
	if err := orch.EnqueueBatch(context.Background(), batchID); err != nil {
		t.Fatalf("enqueue batch: %v", err)
	}

	waitForStatus(t, module, batchID, trackID, ingestionbatch.StatusIngested)
	view, err := module.GetBatch(context.Background(), batchID)
	if err != nil {
		t.Fatalf("get batch: %v", err)
	}
	if view.Running {
		t.Fatalf("expected batch to finish running")
	}
}

func TestOrchestratorMarksError(t *testing.T) {
	module := ingestionbatch.NewModule(nil)
	batchID, _ := module.CreateBatch(context.Background())
	trackID, _ := module.AddToBatch(context.Background(), batchID, ingestionbatch.AddStagedTrackInput{
		SourceURL: "https://example.com",
		Metadata: ingestionbatch.TrackMetadata{
			Title:  "Track",
			Artist: "Artist",
		},
	})
	_ = module.StartRun(context.Background(), batchID)

	orch := New(fakeAdapter{downloadErr: errors.New("fail")}, module, noopHistory{}, "mp3-320", 1)
	_ = orch.EnqueueBatch(context.Background(), batchID)

	waitForStatus(t, module, batchID, trackID, ingestionbatch.StatusError)
}

func waitForStatus(t *testing.T, module *ingestionbatch.Module, batchID ingestionbatch.BatchID, trackID ingestionbatch.TrackID, expected ingestionbatch.IngestionStatus) {
	t.Helper()
	deadline := time.After(2 * time.Second)
	for {
		select {
		case <-deadline:
			t.Fatalf("timeout waiting for status %s", expected)
		default:
			view, err := module.GetBatch(context.Background(), batchID)
			if err != nil {
				t.Fatalf("get batch: %v", err)
			}
			for _, track := range view.Tracks {
				if track.ID == trackID && track.Status == expected {
					return
				}
			}
			time.Sleep(25 * time.Millisecond)
		}
	}
}
