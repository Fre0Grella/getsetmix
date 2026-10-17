package setup

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"strings"
)

// asset is a file Setup downloads for "Just this computer": the GetSetMix
// app itself, and the ffmpeg and Deno it needs.
type asset struct {
	URL    string
	SHA256 string // empty for GetSetMix's own release files (same HTTPS source as Setup)
	// Extract lists the files to take out of a zip, by base name, into the
	// destination folder. Empty: the download is the file.
	Extract []string
}

// Tools pinned by checksum. Bump deliberately; `go test ./internal/setup`
// has a check that every pinned URL still answers (with -tools).
var tools = map[string]map[string][]asset{
	"windows/amd64": {
		"ffmpeg": {{
			URL:     "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip",
			SHA256:  "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba",
			Extract: []string{"ffmpeg.exe", "ffprobe.exe"},
		}},
		"deno": {{
			URL:     "https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-pc-windows-msvc.zip",
			SHA256:  "a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238",
			Extract: []string{"deno.exe"},
		}},
	},
	"darwin/arm64": {
		"ffmpeg": {
			{
				URL:     "https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffmpeg.zip",
				SHA256:  "c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924",
				Extract: []string{"ffmpeg"},
			},
			{
				URL:     "https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/ffprobe.zip",
				SHA256:  "fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6",
				Extract: []string{"ffprobe"},
			},
		},
		"deno": {{
			URL:     "https://github.com/denoland/deno/releases/download/v2.9.7/deno-aarch64-apple-darwin.zip",
			SHA256:  "5cd46d6268f6f78f5d88bdc7159d20bd44cdaa4b3303474839f87ec6fe7ae25c",
			Extract: []string{"deno"},
		}},
	},
}

// appAsset is the GetSetMix release file for this platform, "" if none.
var appAssets = map[string]string{
	"windows/amd64": "getsetmix-windows-x64.exe",
	"darwin/arm64":  "getsetmix-macos-arm64",
}

// fetchAsset downloads a into dir (verifying its checksum), calling progress
// with the fraction done. dest names the file when nothing is extracted.
func fetchAsset(ctx context.Context, a asset, dir, dest string, progress func(float64)) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, ".download-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	sum, err := download(ctx, a.URL, tmp, progress)
	if cerr := tmp.Close(); err == nil {
		err = cerr
	}
	if err != nil {
		return err
	}
	if a.SHA256 != "" && !strings.EqualFold(sum, a.SHA256) {
		return fmt.Errorf("%s: checksum mismatch (got %s), not using it", path.Base(a.URL), sum)
	}
	if len(a.Extract) == 0 {
		return replace(tmp.Name(), filepath.Join(dir, dest))
	}
	return extract(tmp.Name(), dir, a.Extract)
}

func download(ctx context.Context, url string, w io.Writer, progress func(float64)) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "GetSetMix-Setup")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("%s: HTTP %d", path.Base(url), resp.StatusCode)
	}
	h := sha256.New()
	pw := &progressWriter{total: resp.ContentLength, report: progress}
	if _, err := io.Copy(io.MultiWriter(w, h, pw), resp.Body); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

type progressWriter struct {
	total, done int64
	last        float64
	report      func(float64)
}

func (p *progressWriter) Write(b []byte) (int, error) {
	p.done += int64(len(b))
	if p.report != nil && p.total > 0 {
		if f := float64(p.done) / float64(p.total); f-p.last >= 0.01 || f >= 1 {
			p.last = f
			p.report(f)
		}
	}
	return len(b), nil
}

// extract copies the named files (matched by base name, anywhere in the
// archive) out of a zip into dir.
func extract(zipPath, dir string, names []string) error {
	zr, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer zr.Close()
	want := map[string]bool{}
	for _, n := range names {
		want[n] = true
	}
	for _, f := range zr.File {
		base := path.Base(f.Name)
		if !want[base] || f.FileInfo().IsDir() {
			continue
		}
		rc, err := f.Open()
		if err != nil {
			return err
		}
		tmp := filepath.Join(dir, "."+base+".part")
		out, err := os.OpenFile(tmp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o755)
		if err == nil {
			_, err = io.Copy(out, rc)
			if cerr := out.Close(); err == nil {
				err = cerr
			}
		}
		rc.Close()
		if err != nil {
			os.Remove(tmp)
			return err
		}
		if err := replace(tmp, filepath.Join(dir, base)); err != nil {
			return err
		}
		delete(want, base)
	}
	if len(want) > 0 {
		var missing []string
		for n := range want {
			missing = append(missing, n)
		}
		return fmt.Errorf("%s doesn't contain %s", filepath.Base(zipPath), strings.Join(missing, ", "))
	}
	return nil
}

// replace moves src over dst, making it executable.
func replace(src, dst string) error {
	_ = os.Chmod(src, 0o755)
	if err := os.Rename(src, dst); err == nil {
		return nil
	}
	// Windows can't rename over a file; and the old one may be running.
	_ = os.Remove(dst + ".old")
	_ = os.Rename(dst, dst+".old")
	return os.Rename(src, dst)
}
