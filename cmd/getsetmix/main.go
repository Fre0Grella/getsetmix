package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/nats-io/nats.go"

	"github.com/Fre0Grella/getsetmix/internal/adapterbus"
	"github.com/Fre0Grella/getsetmix/internal/history"
	"github.com/Fre0Grella/getsetmix/internal/ingestionbatch"
	"github.com/Fre0Grella/getsetmix/internal/orchestrator"
	"github.com/Fre0Grella/getsetmix/internal/service"
	"github.com/Fre0Grella/getsetmix/internal/tagger"
)

func main() {
	cfg, err := service.LoadConfig()
	if err != nil {
		log.Fatal(err)
	}

	stateDir := os.Getenv("GSM_STATE_DIR")
	if stateDir == "" {
		stateDir = "/data"
	}
	historyStore, err := history.Open(stateDir)
	if err != nil {
		log.Fatal(err)
	}
	defer func() {
		_ = historyStore.Close()
	}()

	natsURL := os.Getenv("GSM_NATS_URL")
	if natsURL == "" {
		natsURL = nats.DefaultURL
	}
	nc, err := nats.Connect(natsURL)
	if err != nil {
		log.Fatal(err)
	}
	defer nc.Close()

	adapterClient := adapterbus.NewNATSClient(nc, adapterbus.Config{
		PreviewSubject:  os.Getenv("GSM_ADAPTER_PREVIEW_SUBJECT"),
		DownloadSubject: os.Getenv("GSM_ADAPTER_DOWNLOAD_SUBJECT"),
		SchemaVersion:   parseIntEnv("GSM_ADAPTER_SCHEMA_VERSION", 1),
	})

	module := ingestionbatch.NewModule(historyStore)
	downloadOrchestrator := orchestrator.New(adapterClient, module, historyStore, tagger.NewID3Tagger(), cfg.OutputFormat, cfg.DownloadConcurrency)

	server := service.NewServer(cfg, module, historyStore, adapterClient, downloadOrchestrator)

	port := parseIntEnv("GSM_HTTP_PORT", 8000)
	httpServer := &http.Server{
		Addr:              fmt.Sprintf(":%d", port),
		Handler:           server.Handler(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	shutdown := make(chan os.Signal, 1)
	signal.Notify(shutdown, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-shutdown
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = httpServer.Shutdown(ctx)
	}()

	log.Printf("getsetmix listening on :%d", port)
	if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}

func parseIntEnv(name string, fallback int) int {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return parsed
}
