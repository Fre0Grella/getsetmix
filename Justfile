test:
    go test ./...
    python -m unittest discover -s adapter-runtime/tests -p "test_*.py"

format:
    gofmt -w .
    python -m black adapter-runtime/src adapter-runtime/tests

lint:
    go vet ./...
    python -m ruff check adapter-runtime/src adapter-runtime/tests

check: lint test

build:
    go build ./cmd/getsetmix

run:
    go run ./cmd/getsetmix

dev:
    mkdir -p .state
    bash -lc 'set -e; trap '\''[ -n "${app_pid:-}" ] && kill "$app_pid" 2>/dev/null || true; [ -n "${adapter_pid:-}" ] && kill "$adapter_pid" 2>/dev/null || true; [ -n "${nats_pid:-}" ] && kill "$nats_pid" 2>/dev/null || true'\'' EXIT INT TERM; go run github.com/nats-io/nats-server/v2@v2.10.18 -p 4222 >/tmp/getsetmix-nats.log 2>&1 & nats_pid=$!; for i in $(seq 1 50); do (echo > /dev/tcp/127.0.0.1/4222) >/dev/null 2>&1 && break; sleep 0.2; done; (cd adapter-runtime && PYTHONPATH=src python -m adapter_runtime >/tmp/getsetmix-adapter.log 2>&1) & adapter_pid=$!; GSM_STATE_DIR="$PWD/.state" GSM_NATS_URL="nats://127.0.0.1:4222" go run ./cmd/getsetmix'

adapter-deps:
    python -m pip install -r adapter-runtime/requirements.txt

adapter-dev-deps:
    python -m pip install -r adapter-runtime/requirements-dev.txt

adapter-run:
    cd adapter-runtime && PYTHONPATH=src python -m adapter_runtime

ci: lint test
