#!/usr/bin/env bash
# Build GetSetMix Setup for the OS this runs on, into companion/dist:
#
#   Windows  GetSetMix-Setup-windows-x64.exe   no console window, with icon
#   macOS    GetSetMix-Setup-macos.zip         "GetSetMix Setup.app", Apple silicon + Intel
#
# Setup is the companion itself: opened with no arguments it shows the
# installer, and it copies itself into place as the companion.
#
# usage: scripts/build-setup.sh [VERSION]     (Windows: from an MSYS2 shell with gcc)
set -euo pipefail
cd "$(dirname "$0")/.."

version="${1:-dev}"
icon="../app/static/assets/icon.png"
flags="-s -w -X main.version=$version"
mkdir -p dist

case "$(go env GOOS)" in
windows)
  # Windows wants four numbers; a dev build is 0.0.0.0.
  winver="0.0.0.0"
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] && winver="$version.0"
  # Icon, version information and manifest go in through .syso files that
  # the linker picks up from the package folder.
  (cd cmd/gsm-companion && go run github.com/tc-hib/go-winres@v0.3.3 simply \
    --arch amd64 --icon "../../$icon" --manifest gui \
    --product-name "GetSetMix Setup" --file-description "GetSetMix Setup" \
    --product-version "$winver" --file-version "$winver" \
    --original-filename "GetSetMix-Setup-windows-x64.exe")
  trap 'rm -f cmd/gsm-companion/rsrc_windows_*.syso' EXIT
  go build -trimpath -ldflags "$flags -H=windowsgui -extldflags=-static" \
    -o dist/GetSetMix-Setup-windows-x64.exe ./cmd/gsm-companion
  echo "built dist/GetSetMix-Setup-windows-x64.exe"
  ;;

darwin)
  export CGO_ENABLED=1 MACOSX_DEPLOYMENT_TARGET=11.0
  app="dist/GetSetMix Setup.app"
  rm -rf "$app" dist/GetSetMix-Setup-macos.zip
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  GOARCH=arm64 CC="clang -arch arm64" go build -trimpath -ldflags "$flags" -o dist/setup-arm64 ./cmd/gsm-companion
  GOARCH=amd64 CC="clang -arch x86_64" go build -trimpath -ldflags "$flags" -o dist/setup-amd64 ./cmd/gsm-companion
  lipo -create -output "$app/Contents/MacOS/GetSetMix Setup" dist/setup-arm64 dist/setup-amd64
  rm dist/setup-arm64 dist/setup-amd64

  iconset="dist/GetSetMix.iconset"
  rm -rf "$iconset" && mkdir -p "$iconset"
  for s in 16 32 128 256 512; do
    sips -z "$s" "$s" "$icon" --out "$iconset/icon_${s}x${s}.png" >/dev/null
    sips -z "$((s * 2))" "$((s * 2))" "$icon" --out "$iconset/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$iconset" -o "$app/Contents/Resources/GetSetMix.icns"
  rm -rf "$iconset"

  short="$version"
  [[ "$short" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || short="0.0.0"
  cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>GetSetMix Setup</string>
<key>CFBundleDisplayName</key><string>GetSetMix Setup</string>
<key>CFBundleIdentifier</key><string>com.getsetmix.setup</string>
<key>CFBundleExecutable</key><string>GetSetMix Setup</string>
<key>CFBundleIconFile</key><string>GetSetMix</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$short</string>
<key>CFBundleVersion</key><string>$short</string>
<key>LSMinimumSystemVersion</key><string>11.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
  # Ad-hoc signature: not notarised (first launch: right-click > Open), but
  # Apple silicon refuses to run unsigned code at all.
  codesign --force --deep --sign - "$app"
  (cd dist && ditto -c -k --keepParent "GetSetMix Setup.app" GetSetMix-Setup-macos.zip)
  echo "built dist/GetSetMix-Setup-macos.zip"
  ;;

*)
  echo "GetSetMix Setup is built for Windows and macOS (where Rekordbox runs)" >&2
  exit 1
  ;;
esac
