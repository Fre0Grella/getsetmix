package setup

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"flag"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

var checkTools = flag.Bool("tools", false, "also check that every pinned tool URL still answers (network)")

func zipOf(t *testing.T, files map[string]string) []byte {
	var b bytes.Buffer
	zw := zip.NewWriter(&b)
	for name, body := range files {
		w, _ := zw.Create(name)
		w.Write([]byte(body))
	}
	zw.Close()
	return b.Bytes()
}

func serve(t *testing.T, body []byte) string {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write(body) }))
	t.Cleanup(srv.Close)
	return srv.URL
}

func TestFetchAssetExtractsAndVerifies(t *testing.T) {
	z := zipOf(t, map[string]string{"ffmpeg-9/bin/ffmpeg.exe": "ff", "ffmpeg-9/bin/ffprobe.exe": "fp", "ffmpeg-9/README": "x"})
	sum := sha256.Sum256(z)
	dir := t.TempDir()
	var last float64
	a := asset{URL: serve(t, z), SHA256: hex.EncodeToString(sum[:]), Extract: []string{"ffmpeg.exe", "ffprobe.exe"}}
	if err := fetchAsset(context.Background(), a, dir, "", func(f float64) { last = f }); err != nil {
		t.Fatal(err)
	}
	for name, want := range map[string]string{"ffmpeg.exe": "ff", "ffprobe.exe": "fp"} {
		if got, _ := os.ReadFile(filepath.Join(dir, name)); string(got) != want {
			t.Errorf("%s = %q", name, got)
		}
	}
	if _, err := os.Stat(filepath.Join(dir, "README")); err == nil {
		t.Error("extracted a file nobody asked for")
	}
	if last != 1 {
		t.Errorf("progress ended at %v", last)
	}
	if entries, _ := filepath.Glob(filepath.Join(dir, ".*")); len(entries) != 0 {
		t.Errorf("leftovers %v", entries)
	}
}

func TestFetchAssetRefusesBadChecksum(t *testing.T) {
	dir := t.TempDir()
	a := asset{URL: serve(t, []byte("tampered")), SHA256: strings.Repeat("0", 64)}
	err := fetchAsset(context.Background(), a, dir, "app.exe", nil)
	if err == nil || !strings.Contains(err.Error(), "checksum") {
		t.Fatalf("err = %v", err)
	}
	if _, err := os.Stat(filepath.Join(dir, "app.exe")); err == nil {
		t.Fatal("kept a file that failed its checksum")
	}
}

func TestFetchAssetMissingMember(t *testing.T) {
	z := zipOf(t, map[string]string{"deno": "d"})
	a := asset{URL: serve(t, z), Extract: []string{"deno.exe"}}
	if err := fetchAsset(context.Background(), a, t.TempDir(), "", nil); err == nil {
		t.Fatal("a zip without the file passed")
	}
}

// go test ./internal/setup -run TestPinnedTools -tools
func TestPinnedTools(t *testing.T) {
	if !*checkTools {
		t.Skip("pass -tools to check the pinned download URLs")
	}
	c := &http.Client{Timeout: 30 * time.Second}
	for plat, byTool := range tools {
		for name, assets := range byTool {
			for _, a := range assets {
				resp, err := c.Head(a.URL)
				if err != nil || resp.StatusCode != http.StatusOK {
					t.Errorf("%s %s: %s: %v %v", plat, name, a.URL, err, resp)
				}
			}
		}
	}
}
