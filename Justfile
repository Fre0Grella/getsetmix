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

adapter-deps:
    python -m pip install -r adapter-runtime/requirements.txt

adapter-dev-deps:
    python -m pip install -r adapter-runtime/requirements-dev.txt

adapter-run:
    python -m adapter_runtime

ci: lint test
