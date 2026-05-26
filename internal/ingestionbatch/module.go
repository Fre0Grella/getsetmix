package ingestionbatch

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"strings"
	"sync"
)

type BatchID string

type TrackID string

type IngestionStatus string

const (
	StatusQueued      IngestionStatus = "queued"
	StatusDownloading IngestionStatus = "downloading"
	StatusTagging     IngestionStatus = "tagging"
	StatusIngested    IngestionStatus = "ingested"
	StatusError       IngestionStatus = "error"
)

var (
	ErrBatchNotFound      = errors.New("ingestion batch not found")
	ErrBatchRunning       = errors.New("ingestion batch is running")
	ErrInvalidStagedTrack = errors.New("invalid staged track")
	ErrDuplicate          = errors.New("duplicate staged track")
	ErrTrackNotFound      = errors.New("staged track not found")
	ErrMetadataLocked     = errors.New("track metadata is locked")
)

type TrackMetadata struct {
	Title  string
	Artist string
	Album  string
	Genre  string
}

type AddStagedTrackInput struct {
	SourceURL string
	Filename  string // optional: proposed output filename for filename-based duplicate detection
	Metadata  TrackMetadata
}

type StagedTrackView struct {
	ID        TrackID
	SourceURL string
	Filename  string
	Metadata  TrackMetadata
	Status    IngestionStatus
	Error     string
}

type BatchView struct {
	ID      BatchID
	Running bool
	Tracks  []StagedTrackView
}

type HistoryStore interface {
	SeenSourceURL(ctx context.Context, sourceURL string) (bool, error)
	SeenFilename(ctx context.Context, filename string) (bool, error)
}

type Module struct {
	mu      sync.Mutex
	history HistoryStore
	batches map[BatchID]*batch
}

type batch struct {
	id      BatchID
	running bool
	tracks  []stagedTrack
}

type stagedTrack struct {
	id            TrackID
	sourceURL     string
	filename      string
	metadata      TrackMetadata
	status        IngestionStatus
	errorMsg      string
	downloadStarted bool
}

func NewModule(history HistoryStore) *Module {
	return &Module{history: history, batches: make(map[BatchID]*batch)}
}

func (m *Module) CreateBatch(ctx context.Context) (BatchID, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	id := BatchID(newID())
	m.batches[id] = &batch{id: id}
	return id, nil
}

func (m *Module) StartRun(ctx context.Context, batchID BatchID) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return ErrBatchNotFound
	}
	if b.running {
		return ErrBatchRunning
	}
	b.running = true
	return nil
}

func (m *Module) FinishRun(ctx context.Context, batchID BatchID) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return ErrBatchNotFound
	}
	b.running = false
	return nil
}

func (m *Module) AddToBatch(ctx context.Context, batchID BatchID, in AddStagedTrackInput) (TrackID, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return "", ErrBatchNotFound
	}
	if b.running {
		return "", ErrBatchRunning
	}
	if strings.TrimSpace(in.SourceURL) == "" {
		return "", ErrInvalidStagedTrack
	}
	if strings.TrimSpace(in.Metadata.Title) == "" || strings.TrimSpace(in.Metadata.Artist) == "" {
		return "", ErrInvalidStagedTrack
	}

	for _, t := range b.tracks {
		if t.sourceURL == in.SourceURL {
			return "", ErrDuplicate
		}
		if in.Filename != "" && t.filename == in.Filename {
			return "", ErrDuplicate
		}
	}
	if m.history != nil {
		if seen, err := m.history.SeenSourceURL(ctx, in.SourceURL); err != nil {
			return "", err
		} else if seen {
			return "", ErrDuplicate
		}
		if in.Filename != "" {
			if seen, err := m.history.SeenFilename(ctx, in.Filename); err != nil {
				return "", err
			} else if seen {
				return "", ErrDuplicate
			}
		}
	}

	id := TrackID(newID())
	b.tracks = append(b.tracks, stagedTrack{
		id:        id,
		sourceURL: in.SourceURL,
		filename:  in.Filename,
		metadata:  in.Metadata,
		status:    StatusQueued,
	})
	return id, nil
}

func (m *Module) UpdateTrackMetadata(ctx context.Context, batchID BatchID, trackID TrackID, md TrackMetadata) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return ErrBatchNotFound
	}
	if strings.TrimSpace(md.Title) == "" || strings.TrimSpace(md.Artist) == "" {
		return ErrInvalidStagedTrack
	}

	for i := range b.tracks {
		if b.tracks[i].id != trackID {
			continue
		}
		if b.tracks[i].downloadStarted || b.tracks[i].status != StatusQueued {
			return ErrMetadataLocked
		}
		b.tracks[i].metadata = md
		return nil
	}
	return ErrTrackNotFound
}

func (m *Module) SetTrackFilename(ctx context.Context, batchID BatchID, trackID TrackID, filename string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return ErrBatchNotFound
	}
	if strings.TrimSpace(filename) == "" {
		return ErrInvalidStagedTrack
	}

	for _, t := range b.tracks {
		if t.id != trackID && t.filename != "" && t.filename == filename {
			return ErrDuplicate
		}
	}
	if m.history != nil {
		if seen, err := m.history.SeenFilename(ctx, filename); err != nil {
			return err
		} else if seen {
			return ErrDuplicate
		}
	}

	for i := range b.tracks {
		if b.tracks[i].id != trackID {
			continue
		}
		if b.tracks[i].downloadStarted || b.tracks[i].status != StatusQueued {
			return ErrMetadataLocked
		}
		b.tracks[i].filename = filename
		return nil
	}
	return ErrTrackNotFound
}

func (m *Module) MarkDownloading(ctx context.Context, batchID BatchID, trackID TrackID) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return ErrBatchNotFound
	}

	for i := range b.tracks {
		if b.tracks[i].id != trackID {
			continue
		}
		if b.tracks[i].status != StatusQueued {
			return ErrInvalidStagedTrack
		}
		b.tracks[i].status = StatusDownloading
		b.tracks[i].downloadStarted = true
		b.tracks[i].errorMsg = ""
		return nil
	}
	return ErrTrackNotFound
}

func (m *Module) MarkTagging(ctx context.Context, batchID BatchID, trackID TrackID) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return ErrBatchNotFound
	}

	for i := range b.tracks {
		if b.tracks[i].id != trackID {
			continue
		}
		if b.tracks[i].status != StatusDownloading {
			return ErrInvalidStagedTrack
		}
		b.tracks[i].status = StatusTagging
		return nil
	}
	return ErrTrackNotFound
}

func (m *Module) MarkIngested(ctx context.Context, batchID BatchID, trackID TrackID) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return ErrBatchNotFound
	}

	for i := range b.tracks {
		if b.tracks[i].id != trackID {
			continue
		}
		if b.tracks[i].status != StatusTagging {
			return ErrInvalidStagedTrack
		}
		b.tracks[i].status = StatusIngested
		return nil
	}
	return ErrTrackNotFound
}

func (m *Module) MarkError(ctx context.Context, batchID BatchID, trackID TrackID, msg string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return ErrBatchNotFound
	}

	for i := range b.tracks {
		if b.tracks[i].id != trackID {
			continue
		}
		if b.tracks[i].status == StatusIngested {
			return ErrInvalidStagedTrack
		}
		b.tracks[i].status = StatusError
		b.tracks[i].errorMsg = strings.TrimSpace(msg)
		return nil
	}
	return ErrTrackNotFound
}

func (m *Module) RetryTrack(ctx context.Context, batchID BatchID, trackID TrackID) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return ErrBatchNotFound
	}

	for i := range b.tracks {
		if b.tracks[i].id != trackID {
			continue
		}
		if b.tracks[i].status != StatusError {
			return ErrInvalidStagedTrack
		}
		b.tracks[i].status = StatusQueued
		b.tracks[i].errorMsg = ""
		return nil
	}
	return ErrTrackNotFound
}

func (m *Module) GetBatch(ctx context.Context, batchID BatchID) (BatchView, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	b := m.batches[batchID]
	if b == nil {
		return BatchView{}, ErrBatchNotFound
	}

	out := BatchView{ID: b.id, Running: b.running}
	out.Tracks = make([]StagedTrackView, 0, len(b.tracks))
	for _, t := range b.tracks {
		out.Tracks = append(out.Tracks, StagedTrackView{
			ID:        t.id,
			SourceURL: t.sourceURL,
			Filename:  t.filename,
			Metadata:  t.metadata,
			Status:    t.status,
			Error:     t.errorMsg,
		})
	}
	return out, nil
}

func newID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}
