FROM golang:1.22-alpine AS build

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/getsetmix ./cmd/getsetmix

FROM gcr.io/distroless/static:nonroot

WORKDIR /
COPY --from=build /out/getsetmix /getsetmix
EXPOSE 8000
USER nonroot:nonroot
ENTRYPOINT ["/getsetmix"]
