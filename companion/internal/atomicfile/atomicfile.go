// Package atomicfile writes a file so that a reader, or a crash, never sees
// half of it: the content goes into a hidden temporary file next to the
// target, which then replaces the target in one rename.
package atomicfile

import (
	"encoding/json"
	"io"
	"os"
	"path/filepath"
)

// Write creates or replaces path with what fill writes into a temporary file
// in the same folder. On any error the temporary file is removed and path is
// left as it was. perm is the new file's mode.
func Write(path string, perm os.FileMode, fill func(w io.Writer) error) error {
	tmp, err := os.CreateTemp(filepath.Dir(path), "."+filepath.Base(path)+".*.gsm-tmp")
	if err != nil {
		return err
	}
	name := tmp.Name()
	err = fill(tmp)
	if cerr := tmp.Close(); err == nil {
		err = cerr
	}
	if err == nil {
		err = os.Chmod(name, perm)
	}
	if err == nil {
		err = os.Rename(name, path)
	}
	if err != nil {
		_ = os.Remove(name)
	}
	return err
}

// WriteFile is os.WriteFile, atomic.
func WriteFile(path string, data []byte, perm os.FileMode) error {
	return Write(path, perm, func(w io.Writer) error {
		_, err := w.Write(data)
		return err
	})
}

// WriteJSON writes v as indented JSON with a final newline, atomically,
// creating path's folder when it is missing.
func WriteJSON(path string, v any) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return WriteFile(path, append(data, '\n'), 0o644)
}
