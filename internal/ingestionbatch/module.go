package ingestionbatch

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"strings"
	"sync"
)

// BatchID is the stable identifier for a single ingestion batch.
type BatchID string

// TrackID identifies a staged track within a batch.
type TrackID string

// IngestionStatus captures the current processing step for a staged track.
type IngestionStatus string

const (
	StatusQueued      IngestionStatus = "queued"
	StatusDownloading IngestionStatus = "downloading"
	StatusTagging     IngestionStatus = "tagging"
	StatusIngested    IngestionStatus = "ingested"
	StatusError       IngestionStatus = "error"
)

var (
	// ErrBatchNotFound is returned when a batch ID does not exist.
	ErrBatchNotFound      = errors.New("ingestion batch not found")
	// ErrBatchRunning is returned when a mutation is attempted while a batch run is active.
	ErrBatchRunning       = errors.New("ingestion batch is running")
	// ErrInvalidStagedTrack is returned when required fields are missing or an invalid transition is attempted.
	ErrInvalidStagedTrack = errors.New("invalid staged track")
	// ErrDuplicate is returned when a staged track conflicts with another by source URL or filename.
	ErrDuplicate          = errors.New("duplicate staged track")
	// ErrTrackNotFound is returned when a track ID is not present in the batch.
	ErrTrackNotFound      = errors.New("staged track not found")
	// ErrMetadataLocked is returned when metadata changes are attempted after downloading starts.
	ErrMetadataLocked     = errors.New("track metadata is locked")
)

// TrackMetadata holds the user-visible fields that drive tagging and deduplication.
type TrackMetadata struct {
	Title  string
	Artist string
	Album  string
	Genre  string
}

// AddStagedTrackInput is the input required to stage a track for ingestion.
type AddStagedTrackInput struct {
	SourceURL string
	Filename  string // optional: proposed output filename for filename-based duplicate detection
	Metadata  TrackMetadata
}

// StagedTrackView is the read-only snapshot of a staged track.
type StagedTrackView struct {
	ID        TrackID
	SourceURL string
	Filename  string
	Metadata  TrackMetadata
	Status    IngestionStatus
	Error     string
}

// BatchView is the read-only snapshot of a batch and its staged tracks.
type BatchView struct {
	ID      BatchID
	Running bool
	Tracks  []StagedTrackView
}

// HistoryStore reports whether a source URL or filename was already ingested.
type HistoryStore interface {
	SeenSourceURL(ctx context.Context, sourceURL string) (bool, error)
	SeenFilename(ctx context.Context, filename string) (bool, error)
}

// Module manages in-memory ingestion batches and their staged tracks.
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
	id              TrackID
	sourceURL       string
	filename        string
	metadata        TrackMetadata
	status          IngestionStatus
	errorMsg        string
	downloadStarted bool
}

// NewModule constructs a batch manager with optional ingestion history.
func NewModule(history HistoryStore) *Module {
	return &Module{history: history, batches: make(map[BatchID]*batch)}
}

// CreateBatch allocates a new empty batch and returns its ID.
func (m *Module) CreateBatch(ctx context.Context) (BatchID, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	id := BatchID(newID())
	m.batches[id] = &batch{id: id}
	return id, nil
}

// StartRun marks a batch as actively ingesting, preventing further staging edits.
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

// FinishRun clears the running flag so staging edits can resume.
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

// AddToBatch validates and stages a track, enforcing duplicate detection.
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

// UpdateTrackMetadata replaces title/artist/album/genre before download starts.
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

// SetTrackFilename assigns a proposed output filename before download starts.
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

// MarkDownloading transitions a queued track into the downloading state.
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

// MarkTagging transitions a downloading track into the tagging state.
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

// MarkIngested marks a tagging track as successfully ingested.
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

// MarkError marks a track as failed and records a short error message.
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

// RetryTrack moves an errored track back to queued while keeping metadata locked.
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

// GetBatch returns a snapshot of the batch and staged tracks for read-only use.
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
