package service

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Config holds server-level configuration.
type Config struct {
	AuthToken           string
	OutputFormat        string
	FilenameTemplate    string
	DownloadConcurrency int
	LibraryRoot         string
	OutputSubdir        string
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
		LibraryRoot:         os.Getenv("GSM_LIBRARY_ROOT"),
		OutputSubdir:        os.Getenv("GSM_OUTPUT_SUBDIR"),
	}, nil
}

// OutputDir resolves the configured output directory for final filenames.
func (c Config) OutputDir() string {
	root := strings.TrimSpace(c.LibraryRoot)
	if root == "" {
		return ""
	}
	subdir := strings.TrimSpace(c.OutputSubdir)
	if subdir == "" {
		return filepath.Clean(root)
	}
	return filepath.Clean(filepath.Join(root, subdir))
}
