package service

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/Fre0Grella/getsetmix/internal/adapterbus"
	"github.com/Fre0Grella/getsetmix/internal/ingestionbatch"
	"github.com/Fre0Grella/getsetmix/internal/orchestrator"
)

type HistoryStore interface {
	ingestionbatch.HistoryStore
	Record(ctx context.Context, sourceURL, filename string) error
}

type Server struct {
	cfg          Config
	batch        *ingestionbatch.Module
	history      HistoryStore
	adapters     adapterbus.Client
	orchestrator *orchestrator.Orchestrator
}

func NewServer(cfg Config, batch *ingestionbatch.Module, history HistoryStore, adapters adapterbus.Client, orchestrator *orchestrator.Orchestrator) *Server {
	return &Server{
		cfg:          cfg,
		batch:        batch,
		history:      history,
		adapters:     adapters,
		orchestrator: orchestrator,
	}
}

func (s *Server) Handler() http.Handler {
	return http.HandlerFunc(s.serveHTTP)
}

func (s *Server) serveHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/health" {
		w.WriteHeader(http.StatusOK)
		return
	}
	if !s.authorized(r) {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}

	switch {
	case r.Method == http.MethodPost && r.URL.Path == "/batches":
		s.handleCreateBatch(w, r)
		return
	case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/start"):
		s.handleStartBatch(w, r)
		return
	case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/batches/") && !strings.Contains(r.URL.Path, "/items/"):
		s.handleGetBatch(w, r)
		return
	case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/retry"):
		s.handleRetry(w, r)
		return
	case r.Method == http.MethodPost && strings.Contains(r.URL.Path, "/items"):
		s.handleAddItem(w, r)
		return
	default:
		writeError(w, http.StatusNotFound, "not found")
	}
}

func (s *Server) authorized(r *http.Request) bool {
	if s.cfg.AuthToken == "" {
		return true
	}
	authHeader := strings.TrimSpace(r.Header.Get("Authorization"))
	expected := "Bearer " + s.cfg.AuthToken
	return authHeader == expected
}

type createBatchResponse struct {
	BatchID string `json:"batch_id"`
}

func (s *Server) handleCreateBatch(w http.ResponseWriter, r *http.Request) {
	id, err := s.batch.CreateBatch(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, createBatchResponse{BatchID: string(id)})
}

type addItemRequest struct {
	SourceURL   string         `json:"source_url"`
	AdapterHint string         `json:"adapter_hint,omitempty"`
	Filename    string         `json:"filename,omitempty"`
	Metadata    *metadataInput `json:"metadata,omitempty"`
}

type metadataInput struct {
	Title  string `json:"title"`
	Artist string `json:"artist"`
	Album  string `json:"album,omitempty"`
	Genre  string `json:"genre,omitempty"`
}

type addItemResponse struct {
	TrackID  string         `json:"track_id"`
	Status   string         `json:"status"`
	Metadata metadataOutput `json:"metadata"`
	Filename string         `json:"filename,omitempty"`
}

type metadataOutput struct {
	Title  string `json:"title"`
	Artist string `json:"artist"`
	Album  string `json:"album,omitempty"`
	Genre  string `json:"genre,omitempty"`
}

func (s *Server) handleAddItem(w http.ResponseWriter, r *http.Request) {
	parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
	if len(parts) < 3 || parts[0] != "batches" || parts[2] != "items" {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	batchID := ingestionbatch.BatchID(parts[1])

	var req addItemRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON")
		return
	}
	if strings.TrimSpace(req.SourceURL) == "" {
		writeError(w, http.StatusBadRequest, "source_url is required")
		return
	}

	md := ingestionbatch.TrackMetadata{}
	if req.Metadata != nil {
		md.Title = strings.TrimSpace(req.Metadata.Title)
		md.Artist = strings.TrimSpace(req.Metadata.Artist)
		md.Album = strings.TrimSpace(req.Metadata.Album)
		md.Genre = strings.TrimSpace(req.Metadata.Genre)
	}
	if md.Title == "" || md.Artist == "" {
		preview, err := s.adapters.Preview(r.Context(), adapterbus.PreviewRequest{
			SourceURL:   req.SourceURL,
			AdapterHint: req.AdapterHint,
		})
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		md.Title = strings.TrimSpace(preview.Metadata.Title)
		md.Artist = strings.TrimSpace(preview.Metadata.Artist)
		md.Album = strings.TrimSpace(preview.Metadata.Album)
		md.Genre = strings.TrimSpace(preview.Metadata.Genre)
	}

	trackID, err := s.batch.AddToBatch(r.Context(), batchID, ingestionbatch.AddStagedTrackInput{
		SourceURL: req.SourceURL,
		Metadata:  md,
	})
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	filename := strings.TrimSpace(req.Filename)
	if filename == "" {
		filename = RenderFilename(s.cfg.FilenameTemplate, req.SourceURL, string(trackID), md)
	}
	filename = EnsureUniqueFilename(s.cfg.OutputDir(), filename)
	if filename != "" {
		if err := s.batch.SetTrackFilename(r.Context(), batchID, trackID, filename); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
	}

	writeJSON(w, http.StatusCreated, addItemResponse{
		TrackID: string(trackID),
		Status:  string(ingestionbatch.StatusQueued),
		Metadata: metadataOutput{
			Title:  md.Title,
			Artist: md.Artist,
			Album:  md.Album,
			Genre:  md.Genre,
		},
		Filename: filename,
	})
}

type startBatchResponse struct {
	BatchID string `json:"batch_id"`
	Running bool   `json:"running"`
}

func (s *Server) handleStartBatch(w http.ResponseWriter, r *http.Request) {
	batchID, err := parseBatchID(r.URL.Path)
	if err != nil {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err := s.batch.StartRun(r.Context(), batchID); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := s.orchestrator.EnqueueBatch(r.Context(), batchID); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusAccepted, startBatchResponse{BatchID: string(batchID), Running: true})
}

type retryResponse struct {
	TrackID string `json:"track_id"`
	Status  string `json:"status"`
}

func (s *Server) handleRetry(w http.ResponseWriter, r *http.Request) {
	batchID, trackID, err := parseRetryPath(r.URL.Path)
	if err != nil {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err := s.batch.RetryTrack(r.Context(), batchID, trackID); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := s.orchestrator.EnqueueTrack(r.Context(), batchID, trackID); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusAccepted, retryResponse{TrackID: string(trackID), Status: string(ingestionbatch.StatusQueued)})
}

type batchResponse struct {
	ID      string          `json:"id"`
	Running bool            `json:"running"`
	Tracks  []trackResponse `json:"tracks"`
}

type trackResponse struct {
	ID        string         `json:"id"`
	SourceURL string         `json:"source_url"`
	Filename  string         `json:"filename,omitempty"`
	Metadata  metadataOutput `json:"metadata"`
	Status    string         `json:"status"`
	Error     string         `json:"error,omitempty"`
}

func (s *Server) handleGetBatch(w http.ResponseWriter, r *http.Request) {
	batchID, err := parseBatchID(r.URL.Path)
	if err != nil {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	view, err := s.batch.GetBatch(r.Context(), batchID)
	if err != nil {
		writeError(w, http.StatusNotFound, err.Error())
		return
	}
	resp := batchResponse{
		ID:      string(view.ID),
		Running: view.Running,
		Tracks:  make([]trackResponse, 0, len(view.Tracks)),
	}
	for _, t := range view.Tracks {
		resp.Tracks = append(resp.Tracks, trackResponse{
			ID:        string(t.ID),
			SourceURL: t.SourceURL,
			Filename:  t.Filename,
			Metadata: metadataOutput{
				Title:  t.Metadata.Title,
				Artist: t.Metadata.Artist,
				Album:  t.Metadata.Album,
				Genre:  t.Metadata.Genre,
			},
			Status: string(t.Status),
			Error:  t.Error,
		})
	}
	writeJSON(w, http.StatusOK, resp)
}

func parseBatchID(path string) (ingestionbatch.BatchID, error) {
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if len(parts) < 2 || parts[0] != "batches" {
		return "", errors.New("invalid")
	}
	return ingestionbatch.BatchID(parts[1]), nil
}

func parseRetryPath(path string) (ingestionbatch.BatchID, ingestionbatch.TrackID, error) {
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if len(parts) != 5 || parts[0] != "batches" || parts[2] != "items" || parts[4] != "retry" {
		return "", "", errors.New("invalid")
	}
	return ingestionbatch.BatchID(parts[1]), ingestionbatch.TrackID(parts[3]), nil
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}
