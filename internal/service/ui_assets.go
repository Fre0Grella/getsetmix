package service

import (
	"embed"
	"io/fs"
	"net/http"
	"strings"
)

//go:embed ui/index.html ui/assets/*
var uiFS embed.FS

var (
	uiRootFS, uiRootErr     = fs.Sub(uiFS, "ui")
	uiAssetsFS, uiAssetsErr = fs.Sub(uiFS, "ui/assets")
)

func (s *Server) serveUI(w http.ResponseWriter, r *http.Request) bool {
	if r.Method != http.MethodGet {
		return false
	}
	if uiRootErr != nil || uiAssetsErr != nil {
		return false
	}
	if r.URL.Path == "/" || r.URL.Path == "/index.html" {
		http.ServeFileFS(w, r, uiRootFS, "index.html")
		return true
	}
	if strings.HasPrefix(r.URL.Path, "/assets/") {
		http.StripPrefix("/assets/", http.FileServer(http.FS(uiAssetsFS))).ServeHTTP(w, r)
		return true
	}
	return false
}
