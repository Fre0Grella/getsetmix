package adapterbus

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"
)

func TestNATSClient_PreviewRoundtrip(t *testing.T) {
	srv := startTestNATSServer(t)
	defer srv.Shutdown()

	nc := connectTestNATS(t, srv)
	defer nc.Close()

	_, err := nc.Subscribe(defaultPreviewSubject, func(msg *nats.Msg) {
		var req PreviewRequest
		if err := json.Unmarshal(msg.Data, &req); err != nil {
			t.Fatalf("unmarshal preview request: %v", err)
		}

		resp := PreviewResponse{
			SchemaVersion: req.SchemaVersion,
			JobID:         req.JobID,
			SourceURL:     req.SourceURL,
			Metadata: Metadata{
				Title:  "Title",
				Artist: "Artist",
				Album:  "Album",
				Genre:  "Genre",
			},
			CoverURL:  "https://img.example/cover.jpg",
			CoverPath: "C:\\staging\\covers\\cover.jpg",
		}
		data, err := json.Marshal(resp)
		if err != nil {
			t.Fatalf("marshal preview response: %v", err)
		}
		_ = msg.Respond(data)
	})
	if err != nil {
		t.Fatalf("subscribe preview: %v", err)
	}

	client := NewNATSClient(nc, Config{SchemaVersion: 1})
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	resp, err := client.Preview(ctx, PreviewRequest{
		JobID:       "job-preview-1",
		SourceURL:   "https://example.test/track/123",
		AdapterHint: "youtube",
	})
	if err != nil {
		t.Fatalf("Preview error: %v", err)
	}
	if resp.Metadata.Title != "Title" || resp.Metadata.Artist != "Artist" {
		t.Fatalf("unexpected metadata: %+v", resp.Metadata)
	}
	if resp.CoverURL == "" || resp.CoverPath == "" {
		t.Fatalf("expected cover references, got url=%q path=%q", resp.CoverURL, resp.CoverPath)
	}
}

func TestNATSClient_DownloadRoundtrip(t *testing.T) {
	srv := startTestNATSServer(t)
	defer srv.Shutdown()

	nc := connectTestNATS(t, srv)
	defer nc.Close()

	_, err := nc.Subscribe(defaultDownloadSubject, func(msg *nats.Msg) {
		var req DownloadRequest
		if err := json.Unmarshal(msg.Data, &req); err != nil {
			t.Fatalf("unmarshal download request: %v", err)
		}

		resp := DownloadResponse{
			SchemaVersion: req.SchemaVersion,
			JobID:         req.JobID,
			SourceURL:     req.SourceURL,
			AudioPath:     "C:\\staging\\audio\\track.mp3",
			CoverPath:     "C:\\staging\\covers\\track.jpg",
		}
		if req.JobID == "job-download-err" {
			resp.Error = "adapter failed"
			resp.AudioPath = ""
			resp.CoverPath = ""
		}
		data, err := json.Marshal(resp)
		if err != nil {
			t.Fatalf("marshal download response: %v", err)
		}
		_ = msg.Respond(data)
	})
	if err != nil {
		t.Fatalf("subscribe download: %v", err)
	}

	client := NewNATSClient(nc, Config{SchemaVersion: 1})
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	resp, err := client.Download(ctx, DownloadRequest{
		JobID:       "job-download-1",
		SourceURL:   "https://example.test/track/456",
		AdapterHint: "soundcloud",
		Metadata: Metadata{
			Title:  "Title",
			Artist: "Artist",
			Album:  "Album",
			Genre:  "Genre",
		},
		OutputFormat: "mp3-320",
	})
	if err != nil {
		t.Fatalf("Download error: %v", err)
	}
	if resp.AudioPath == "" {
		t.Fatalf("expected audio path")
	}
	if resp.CoverPath == "" {
		t.Fatalf("expected cover path")
	}

	_, err = client.Download(ctx, DownloadRequest{
		JobID:       "job-download-err",
		SourceURL:   "https://example.test/track/789",
		AdapterHint: "soundcloud",
		Metadata: Metadata{
			Title:  "Title",
			Artist: "Artist",
		},
		OutputFormat: "mp3-320",
	})
	if err == nil {
		t.Fatalf("expected download error to propagate")
	}
}

func startTestNATSServer(t *testing.T) *server.Server {
	t.Helper()

	opts := &server.Options{Port: -1}
	srv, err := server.NewServer(opts)
	if err != nil {
		t.Fatalf("new NATS server: %v", err)
	}
	go srv.Start()
	if !srv.ReadyForConnections(10 * time.Second) {
		t.Fatalf("nats server not ready")
	}
	return srv
}

func connectTestNATS(t *testing.T, srv *server.Server) *nats.Conn {
	t.Helper()

	nc, err := nats.Connect(srv.ClientURL())
	if err != nil {
		t.Fatalf("connect NATS: %v", err)
	}
	return nc
}
