package history

import (
	"context"
	"database/sql"
	"fmt"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite"
)

// Store persists ingested source URLs and filenames for duplicate detection.
type Store struct {
	db *sql.DB
}

// Open creates or opens the history database inside the provided state directory.
func Open(stateDir string) (*Store, error) {
	if stateDir == "" {
		return nil, fmt.Errorf("state directory is required")
	}
	dbPath := filepath.Join(stateDir, "history.db")
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, err
	}
	store := &Store{db: db}
	if err := store.ensureSchema(context.Background()); err != nil {
		_ = db.Close()
		return nil, err
	}
	return store, nil
}

// Close releases the underlying database connection.
func (s *Store) Close() error {
	if s == nil || s.db == nil {
		return nil
	}
	return s.db.Close()
}

// SeenSourceURL reports whether the URL was already ingested.
func (s *Store) SeenSourceURL(ctx context.Context, sourceURL string) (bool, error) {
	return s.exists(ctx, "SELECT 1 FROM ingested_urls WHERE source_url = ? LIMIT 1", sourceURL)
}

// SeenFilename reports whether the filename was already ingested.
func (s *Store) SeenFilename(ctx context.Context, filename string) (bool, error) {
	return s.exists(ctx, "SELECT 1 FROM ingested_filenames WHERE filename = ? LIMIT 1", filename)
}

// Record persists a source URL and filename after successful ingestion.
func (s *Store) Record(ctx context.Context, sourceURL, filename string) error {
	now := time.Now().UTC().Format(time.RFC3339)
	if sourceURL != "" {
		if _, err := s.db.ExecContext(ctx,
			"INSERT OR IGNORE INTO ingested_urls (source_url, ingested_at) VALUES (?, ?)",
			sourceURL, now,
		); err != nil {
			return err
		}
	}
	if filename != "" {
		if _, err := s.db.ExecContext(ctx,
			"INSERT OR IGNORE INTO ingested_filenames (filename, ingested_at) VALUES (?, ?)",
			filename, now,
		); err != nil {
			return err
		}
	}
	return nil
}

func (s *Store) ensureSchema(ctx context.Context) error {
	if _, err := s.db.ExecContext(ctx, `
        CREATE TABLE IF NOT EXISTS ingested_urls (
            source_url TEXT PRIMARY KEY,
            ingested_at TEXT NOT NULL
        );
    `); err != nil {
		return err
	}
	if _, err := s.db.ExecContext(ctx, `
        CREATE TABLE IF NOT EXISTS ingested_filenames (
            filename TEXT PRIMARY KEY,
            ingested_at TEXT NOT NULL
        );
    `); err != nil {
		return err
	}
	return nil
}

func (s *Store) exists(ctx context.Context, query string, arg string) (bool, error) {
	if s == nil || s.db == nil {
		return false, fmt.Errorf("history store not initialized")
	}
	var marker int
	err := s.db.QueryRowContext(ctx, query, arg).Scan(&marker)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}
