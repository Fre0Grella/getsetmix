package service

import (
	"fmt"
	"os"
	"strconv"
)

// Config holds server-level configuration.
type Config struct {
	AuthToken           string
	OutputFormat        string
	FilenameTemplate    string
	DownloadConcurrency int
}

// LoadConfig reads configuration from environment variables.
func LoadConfig() (Config, error) {
	concurrency := 2
	if raw := os.Getenv("GSM_DOWNLOAD_CONCURRENCY_DEFAULT"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil {
			return Config{}, fmt.Errorf("invalid GSM_DOWNLOAD_CONCURRENCY_DEFAULT: %w", err)
		}
		concurrency = parsed
	}
	outputFormat := os.Getenv("GSM_OUTPUT_FORMAT")
	if outputFormat == "" {
		outputFormat = "mp3-320"
	}
	return Config{
		AuthToken:           os.Getenv("GSM_AUTH_TOKEN"),
		OutputFormat:        outputFormat,
		FilenameTemplate:    os.Getenv("GSM_FILENAME_TEMPLATE"),
		DownloadConcurrency: concurrency,
	}, nil
}
