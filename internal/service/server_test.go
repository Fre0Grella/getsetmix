package service

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Fre0Grella/getsetmix/internal/adapterbus"
	"github.com/Fre0Grella/getsetmix/internal/ingestionbatch"
	"github.com/Fre0Grella/getsetmix/internal/orchestrator"
)

type fakeAdapterClient struct {
	previewFn  func(req adapterbus.PreviewRequest) (adapterbus.PreviewResponse, error)
	downloadFn func(req adapterbus.DownloadRequest) (adapterbus.DownloadResponse, error)
}

func (f fakeAdapterClient) Preview(ctx context.Context, req adapterbus.PreviewRequest) (adapterbus.PreviewResponse, error) {
	return f.previewFn(req)
}

func (f fakeAdapterClient) Download(ctx context.Context, req adapterbus.DownloadRequest) (adapterbus.DownloadResponse, error) {
	return f.downloadFn(req)
}

type memoryHistory struct {
	seenURLs      map[string]bool
	seenFilenames map[string]bool
}

func newMemoryHistory() *memoryHistory {
	return &memoryHistory{
		seenURLs:      make(map[string]bool),
		seenFilenames: make(map[string]bool),
	}
}

func (m *memoryHistory) SeenSourceURL(ctx context.Context, sourceURL string) (bool, error) {
	return m.seenURLs[sourceURL], nil
}

func (m *memoryHistory) SeenFilename(ctx context.Context, filename string) (bool, error) {
	return m.seenFilenames[filename], nil
}

func (m *memoryHistory) Record(ctx context.Context, sourceURL, filename string) error {
	if sourceURL != "" {
		m.seenURLs[sourceURL] = true
	}
	if filename != "" {
		m.seenFilenames[filename] = true
	}
	return nil
}

func TestServerBatchLifecycle(t *testing.T) {
	adapter := fakeAdapterClient{
		previewFn: func(req adapterbus.PreviewRequest) (adapterbus.PreviewResponse, error) {
			return adapterbus.PreviewResponse{
				Metadata: adapterbus.Metadata{Title: "Track", Artist: "Artist"},
			}, nil
		},
		downloadFn: func(req adapterbus.DownloadRequest) (adapterbus.DownloadResponse, error) {
			return adapterbus.DownloadResponse{AudioPath: "/tmp/audio.mp3"}, nil
		},
	}
	history := newMemoryHistory()
	module := ingestionbatch.NewModule(history)
	orch := orchestrator.New(adapter, module, history, "mp3-320", 1)
	server := NewServer(Config{FilenameTemplate: "{title} - {artist}"}, module, history, adapter, orch)

	ts := httptest.NewServer(server.Handler())
	defer ts.Close()

	batchID := createBatch(t, ts.URL)
	trackID := addItem(t, ts.URL, batchID, map[string]any{"source_url": "https://example.com"})
	startBatch(t, ts.URL, batchID)

	waitForBatchStatus(t, ts.URL, batchID, trackID, "ingested")
}

func TestServerRetry(t *testing.T) {
	callCount := 0
	adapter := fakeAdapterClient{
		previewFn: func(req adapterbus.PreviewRequest) (adapterbus.PreviewResponse, error) {
			return adapterbus.PreviewResponse{
				Metadata: adapterbus.Metadata{Title: "Track", Artist: "Artist"},
			}, nil
		},
		downloadFn: func(req adapterbus.DownloadRequest) (adapterbus.DownloadResponse, error) {
			callCount++
			if callCount == 1 {
				return adapterbus.DownloadResponse{}, errors.New("boom")
			}
			return adapterbus.DownloadResponse{AudioPath: "/tmp/audio.mp3"}, nil
		},
	}
	history := newMemoryHistory()
	module := ingestionbatch.NewModule(history)
	orch := orchestrator.New(adapter, module, history, "mp3-320", 1)
	server := NewServer(Config{}, module, history, adapter, orch)

	ts := httptest.NewServer(server.Handler())
	defer ts.Close()

	batchID := createBatch(t, ts.URL)
	trackID := addItem(t, ts.URL, batchID, map[string]any{"source_url": "https://example.com"})
	startBatch(t, ts.URL, batchID)
	waitForBatchStatus(t, ts.URL, batchID, trackID, "error")

	retryTrack(t, ts.URL, batchID, trackID)
	waitForBatchStatus(t, ts.URL, batchID, trackID, "ingested")
}

func TestServerAuth(t *testing.T) {
	adapter := fakeAdapterClient{
		previewFn: func(req adapterbus.PreviewRequest) (adapterbus.PreviewResponse, error) {
			return adapterbus.PreviewResponse{}, nil
		},
		downloadFn: func(req adapterbus.DownloadRequest) (adapterbus.DownloadResponse, error) {
			return adapterbus.DownloadResponse{}, nil
		},
	}
	history := newMemoryHistory()
	module := ingestionbatch.NewModule(history)
	orch := orchestrator.New(adapter, module, history, "mp3-320", 1)
	server := NewServer(Config{AuthToken: "secret"}, module, history, adapter, orch)

	ts := httptest.NewServer(server.Handler())
	defer ts.Close()

	resp, err := http.Post(ts.URL+"/batches", "application/json", bytes.NewBufferString("{}"))
	if err != nil {
		t.Fatalf("post: %v", err)
	}
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", resp.StatusCode)
	}
}

func TestServerUI(t *testing.T) {
	adapter := fakeAdapterClient{
		previewFn: func(req adapterbus.PreviewRequest) (adapterbus.PreviewResponse, error) {
			return adapterbus.PreviewResponse{}, nil
		},
		downloadFn: func(req adapterbus.DownloadRequest) (adapterbus.DownloadResponse, error) {
			return adapterbus.DownloadResponse{}, nil
		},
	}
	history := newMemoryHistory()
	module := ingestionbatch.NewModule(history)
	orch := orchestrator.New(adapter, module, history, "mp3-320", 1)
	server := NewServer(Config{}, module, history, adapter, orch)

	ts := httptest.NewServer(server.Handler())
	defer ts.Close()

	resp, err := http.Get(ts.URL + "/")
	if err != nil {
		t.Fatalf("get ui: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("ui status: %d", resp.StatusCode)
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read ui: %v", err)
	}
	if !bytes.Contains(body, []byte("Getsetmix")) {
		t.Fatalf("expected UI content")
	}
}

func createBatch(t *testing.T, baseURL string) string {
	t.Helper()
	resp, err := http.Post(baseURL+"/batches", "application/json", bytes.NewBufferString("{}"))
	if err != nil {
		t.Fatalf("create batch: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("create batch status: %d", resp.StatusCode)
	}
	var body struct {
		BatchID string `json:"batch_id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decode batch: %v", err)
	}
	return body.BatchID
}

func addItem(t *testing.T, baseURL, batchID string, payload map[string]any) string {
	t.Helper()
	data, _ := json.Marshal(payload)
	resp, err := http.Post(baseURL+"/batches/"+batchID+"/items", "application/json", bytes.NewBuffer(data))
	if err != nil {
		t.Fatalf("add item: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("add item status: %d", resp.StatusCode)
	}
	var body struct {
		TrackID string `json:"track_id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decode add item: %v", err)
	}
	return body.TrackID
}

func startBatch(t *testing.T, baseURL, batchID string) {
	t.Helper()
	resp, err := http.Post(baseURL+"/batches/"+batchID+"/start", "application/json", bytes.NewBufferString("{}"))
	if err != nil {
		t.Fatalf("start batch: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusAccepted {
		t.Fatalf("start batch status: %d", resp.StatusCode)
	}
}

func retryTrack(t *testing.T, baseURL, batchID, trackID string) {
	t.Helper()
	resp, err := http.Post(baseURL+"/batches/"+batchID+"/items/"+trackID+"/retry", "application/json", bytes.NewBufferString("{}"))
	if err != nil {
		t.Fatalf("retry: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusAccepted {
		t.Fatalf("retry status: %d", resp.StatusCode)
	}
}

func waitForBatchStatus(t *testing.T, baseURL, batchID, trackID, expected string) {
	t.Helper()
	timeout := time.After(2 * time.Second)
	for {
		select {
		case <-timeout:
			t.Fatalf("timeout waiting for status %s", expected)
		default:
			resp, err := http.Get(baseURL + "/batches/" + batchID)
			if err != nil {
				t.Fatalf("get batch: %v", err)
			}
			var body struct {
				Tracks []struct {
					ID     string `json:"id"`
					Status string `json:"status"`
				} `json:"tracks"`
			}
			if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
				resp.Body.Close()
				t.Fatalf("decode batch: %v", err)
			}
			resp.Body.Close()
			for _, track := range body.Tracks {
				if track.ID == trackID && track.Status == expected {
					return
				}
			}
			time.Sleep(25 * time.Millisecond)
		}
	}
}
