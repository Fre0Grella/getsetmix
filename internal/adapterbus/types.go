package adapterbus

// Metadata carries the user-facing tagging fields for an adapter response.
type Metadata struct {
	Title  string `json:"title"`
	Artist string `json:"artist"`
	Album  string `json:"album,omitempty"`
	Genre  string `json:"genre,omitempty"`
}

// PreviewRequest asks the Adapter Runtime to fetch metadata for a source URL.
type PreviewRequest struct {
	SchemaVersion int    `json:"schema_version"`
	JobID         string `json:"job_id"`
	SourceURL     string `json:"source_url"`
	AdapterHint   string `json:"adapter_hint,omitempty"`
}

// PreviewResponse returns metadata plus optional cover references.
type PreviewResponse struct {
	SchemaVersion int      `json:"schema_version"`
	JobID         string   `json:"job_id"`
	SourceURL     string   `json:"source_url"`
	Metadata      Metadata `json:"metadata"`
	CoverURL      string   `json:"cover_url,omitempty"`
	CoverPath     string   `json:"cover_path,omitempty"`
	Error         string   `json:"error,omitempty"`
}

// DownloadRequest asks the Adapter Runtime to download assets for a source URL.
type DownloadRequest struct {
	SchemaVersion int      `json:"schema_version"`
	JobID         string   `json:"job_id"`
	SourceURL     string   `json:"source_url"`
	AdapterHint   string   `json:"adapter_hint,omitempty"`
	Metadata      Metadata `json:"metadata"`
	OutputFormat  string   `json:"output_format"`
}

// DownloadResponse returns file paths for downloaded assets.
type DownloadResponse struct {
	SchemaVersion int    `json:"schema_version"`
	JobID         string `json:"job_id"`
	SourceURL     string `json:"source_url"`
	AudioPath     string `json:"audio_path,omitempty"`
	CoverPath     string `json:"cover_path,omitempty"`
	Error         string `json:"error,omitempty"`
}
