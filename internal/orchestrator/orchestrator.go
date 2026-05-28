package orchestrator

import (
	"context"
	"fmt"
	"sync"

	"github.com/Fre0Grella/getsetmix/internal/adapterbus"
	"github.com/Fre0Grella/getsetmix/internal/ingestionbatch"
	"github.com/Fre0Grella/getsetmix/internal/tagger"
)

// BatchModule defines the ingestion batch operations the orchestrator needs.
type BatchModule interface {
	MarkDownloading(ctx context.Context, batchID ingestionbatch.BatchID, trackID ingestionbatch.TrackID) error
	MarkTagging(ctx context.Context, batchID ingestionbatch.BatchID, trackID ingestionbatch.TrackID) error
	MarkIngested(ctx context.Context, batchID ingestionbatch.BatchID, trackID ingestionbatch.TrackID) error
	MarkError(ctx context.Context, batchID ingestionbatch.BatchID, trackID ingestionbatch.TrackID, msg string) error
	FinishRun(ctx context.Context, batchID ingestionbatch.BatchID) error
	GetBatch(ctx context.Context, batchID ingestionbatch.BatchID) (ingestionbatch.BatchView, error)
}

// HistoryRecorder stores completed ingestions.
type HistoryRecorder interface {
	Record(ctx context.Context, sourceURL, filename string) error
}

// Tagger writes metadata into downloaded audio files.
type Tagger interface {
	Tag(ctx context.Context, audioPath string, metadata tagger.Metadata, sourceURL, coverPath string) error
}

type task struct {
	batchID   ingestionbatch.BatchID
	trackID   ingestionbatch.TrackID
	sourceURL string
	filename  string
	metadata  ingestionbatch.TrackMetadata
}

// Orchestrator runs downloads with bounded concurrency and updates ingestion status.
type Orchestrator struct {
	client       adapterbus.Client
	batch        BatchModule
	history      HistoryRecorder
	tagger       Tagger
	outputFormat string

	queue chan task

	mu            sync.Mutex
	activeByBatch map[ingestionbatch.BatchID]int
}

// New creates an orchestrator and starts worker goroutines.
func New(client adapterbus.Client, batch BatchModule, history HistoryRecorder, tagger Tagger, outputFormat string, concurrency int) *Orchestrator {
	if concurrency <= 0 {
		concurrency = 1
	}
	o := &Orchestrator{
		client:        client,
		batch:         batch,
		history:       history,
		tagger:        tagger,
		outputFormat:  outputFormat,
		queue:         make(chan task, concurrency*4),
		activeByBatch: make(map[ingestionbatch.BatchID]int),
	}
	for i := 0; i < concurrency; i++ {
		go o.worker()
	}
	return o
}

// EnqueueBatch schedules all queued tracks in the batch for download.
func (o *Orchestrator) EnqueueBatch(ctx context.Context, batchID ingestionbatch.BatchID) error {
	view, err := o.batch.GetBatch(ctx, batchID)
	if err != nil {
		return err
	}
	queued := 0
	for _, track := range view.Tracks {
		if track.Status != ingestionbatch.StatusQueued {
			continue
		}
		queued++
		o.enqueue(task{
			batchID:   batchID,
			trackID:   track.ID,
			sourceURL: track.SourceURL,
			filename:  track.Filename,
			metadata:  track.Metadata,
		})
	}
	if queued == 0 {
		return o.batch.FinishRun(ctx, batchID)
	}
	return nil
}

// EnqueueTrack schedules a single queued track for download.
func (o *Orchestrator) EnqueueTrack(ctx context.Context, batchID ingestionbatch.BatchID, trackID ingestionbatch.TrackID) error {
	view, err := o.batch.GetBatch(ctx, batchID)
	if err != nil {
		return err
	}
	for _, track := range view.Tracks {
		if track.ID != trackID {
			continue
		}
		if track.Status != ingestionbatch.StatusQueued {
			return fmt.Errorf("track is not queued")
		}
		o.enqueue(task{
			batchID:   batchID,
			trackID:   track.ID,
			sourceURL: track.SourceURL,
			filename:  track.Filename,
			metadata:  track.Metadata,
		})
		return nil
	}
	return ingestionbatch.ErrTrackNotFound
}

func (o *Orchestrator) enqueue(t task) {
	o.mu.Lock()
	o.activeByBatch[t.batchID]++
	o.mu.Unlock()
	o.queue <- t
}

func (o *Orchestrator) worker() {
	for t := range o.queue {
		o.process(t)
		o.decrement(t.batchID)
	}
}

func (o *Orchestrator) process(t task) {
	ctx := context.Background()
	if err := o.batch.MarkDownloading(ctx, t.batchID, t.trackID); err != nil {
		_ = o.batch.MarkError(ctx, t.batchID, t.trackID, err.Error())
		return
	}
	req := adapterbus.DownloadRequest{
		JobID:        string(t.trackID),
		SourceURL:    t.sourceURL,
		Metadata:     adapterbus.Metadata{Title: t.metadata.Title, Artist: t.metadata.Artist, Album: t.metadata.Album, Genre: t.metadata.Genre},
		OutputFormat: o.outputFormat,
	}
	downloadResp, err := o.client.Download(ctx, req)
	if err != nil {
		_ = o.batch.MarkError(ctx, t.batchID, t.trackID, err.Error())
		return
	}
	if err := o.batch.MarkTagging(ctx, t.batchID, t.trackID); err != nil {
		_ = o.batch.MarkError(ctx, t.batchID, t.trackID, err.Error())
		return
	}
	if o.tagger != nil {
		if err := o.tagger.Tag(ctx, downloadResp.AudioPath, tagger.Metadata{
			Title:  t.metadata.Title,
			Artist: t.metadata.Artist,
			Album:  t.metadata.Album,
			Genre:  t.metadata.Genre,
		}, t.sourceURL, downloadResp.CoverPath); err != nil {
			_ = o.batch.MarkError(ctx, t.batchID, t.trackID, err.Error())
			return
		}
	}
	if err := o.batch.MarkIngested(ctx, t.batchID, t.trackID); err != nil {
		_ = o.batch.MarkError(ctx, t.batchID, t.trackID, err.Error())
		return
	}
	if o.history != nil {
		_ = o.history.Record(ctx, t.sourceURL, t.filename)
	}
}

func (o *Orchestrator) decrement(batchID ingestionbatch.BatchID) {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.activeByBatch[batchID]--
	if o.activeByBatch[batchID] > 0 {
		return
	}
	delete(o.activeByBatch, batchID)
	_ = o.batch.FinishRun(context.Background(), batchID)
}
