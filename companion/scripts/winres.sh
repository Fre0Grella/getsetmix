#!/usr/bin/env bash
# Give the next `go build ./cmd/gsm-companion` for Windows an icon, version
# information and a manifest, through the .syso files go-winres writes into
# the package folder (the linker picks them up from there). Antivirus
# heuristics distrust executables without them (issue #16).
#
# The caller removes cmd/gsm-companion/rsrc_windows_*.syso afterwards.
#
# usage: scripts/winres.sh VERSION cli|gui ORIGINAL-FILENAME PRODUCT-NAME [DESCRIPTION]
set -euo pipefail
cd "$(dirname "$0")/../cmd/gsm-companion"

version="$1" manifest="$2" filename="$3" product="$4" description="${5:-$4}"
# Windows wants four numbers: 1.2.3 and 1.2.3-rc.1 become 1.2.3.0, a dev
# build 0.0.0.0.
winver="0.0.0.0"
[[ "${version%%-*}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] && winver="${version%%-*}.0"

go run github.com/tc-hib/go-winres@v0.3.3 simply \
  --arch amd64 --icon ../../../app/static/assets/icon.png --manifest "$manifest" \
  --product-name "$product" --file-description "$description" \
  --product-version "$winver" --file-version "$winver" \
  --original-filename "$filename"
