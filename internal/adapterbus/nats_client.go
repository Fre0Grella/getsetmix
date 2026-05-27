package adapterbus

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/nats-io/nats.go"
)

const (
	defaultPreviewSubject  = "adapter.preview"
	defaultDownloadSubject = "adapter.download"
)

// Client defines the adapter runtime request/response API.
type Client interface {
	Preview(ctx context.Context, req PreviewRequest) (PreviewResponse, error)
	Download(ctx context.Context, req DownloadRequest) (DownloadResponse, error)
}

// Config configures the NATS-backed adapter bus client.
type Config struct {
	PreviewSubject  string
	DownloadSubject string
	SchemaVersion   int
}

// NATSClient implements Client using NATS request/reply.
type NATSClient struct {
	nc              *nats.Conn
	previewSubject  string
	downloadSubject string
	schemaVersion   int
}

// NewNATSClient returns a NATS-backed adapter bus client.
func NewNATSClient(nc *nats.Conn, cfg Config) *NATSClient {
	previewSubject := cfg.PreviewSubject
	if previewSubject == "" {
		previewSubject = defaultPreviewSubject
	}
	downloadSubject := cfg.DownloadSubject
	if downloadSubject == "" {
		downloadSubject = defaultDownloadSubject
	}
	schemaVersion := cfg.SchemaVersion
	if schemaVersion == 0 {
		schemaVersion = 1
	}
	return &NATSClient{
		nc:              nc,
		previewSubject:  previewSubject,
		downloadSubject: downloadSubject,
		schemaVersion:   schemaVersion,
	}
}

// Preview requests metadata preview data from the Adapter Runtime.
func (c *NATSClient) Preview(ctx context.Context, req PreviewRequest) (PreviewResponse, error) {
	req.SchemaVersion = c.ensureSchema(req.SchemaVersion)
	payload, err := json.Marshal(req)
	if err != nil {
		return PreviewResponse{}, err
	}

	msg := nats.NewMsg(c.previewSubject)
	msg.Data = payload

	respMsg, err := c.nc.RequestMsgWithContext(ctx, msg)
	if err != nil {
		return PreviewResponse{}, err
	}

	var resp PreviewResponse
	if err := json.Unmarshal(respMsg.Data, &resp); err != nil {
		return PreviewResponse{}, err
	}
	if resp.Error != "" {
		return resp, errors.New(resp.Error)
	}
	return resp, nil
}

// Download requests audio and cover assets from the Adapter Runtime.
func (c *NATSClient) Download(ctx context.Context, req DownloadRequest) (DownloadResponse, error) {
	req.SchemaVersion = c.ensureSchema(req.SchemaVersion)
	payload, err := json.Marshal(req)
	if err != nil {
		return DownloadResponse{}, err
	}

	msg := nats.NewMsg(c.downloadSubject)
	msg.Data = payload

	respMsg, err := c.nc.RequestMsgWithContext(ctx, msg)
	if err != nil {
		return DownloadResponse{}, err
	}

	var resp DownloadResponse
	if err := json.Unmarshal(respMsg.Data, &resp); err != nil {
		return DownloadResponse{}, err
	}
	if resp.Error != "" {
		return resp, errors.New(resp.Error)
	}
	return resp, nil
}

func (c *NATSClient) ensureSchema(schemaVersion int) int {
	if schemaVersion == 0 {
		return c.schemaVersion
	}
	return schemaVersion
}
