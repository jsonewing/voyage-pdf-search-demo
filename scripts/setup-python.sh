#!/usr/bin/env bash
# Install the pinned standalone Python used by run.sh.
# Requires only curl and tar and is idempotent after the first successful run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR_DIR="$PROJECT_DIR/vendor"
DOWNLOADS_DIR="$VENDOR_DIR/_downloads"
PYTHON_DIR="$VENDOR_DIR/python"

# Pinned python-build-standalone release. Update both values together only
# after rebuilding the distribution and running its verification suite.
PBS_RELEASE="20260610"
PBS_PY_VERSION="3.12.13"

for command_name in curl tar; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "ERROR: '$command_name' is required for first-run setup." >&2
    exit 1
  fi
done

case "$(uname -s)/$(uname -m)" in
  Darwin/arm64)
    platform="aarch64-apple-darwin"
    expected_sha256="e18ddd4c1e8f4a1d6c4590b37f423d76aec734447edc20ed08e93983d95f2132"
    ;;
  Darwin/x86_64)
    platform="x86_64-apple-darwin"
    expected_sha256="ba02164e4db381af8c288c0bc1657584a835e9121a0fa2836b0f2e712ff8cdf5"
    ;;
  Linux/aarch64|Linux/arm64)
    platform="aarch64-unknown-linux-gnu"
    expected_sha256="bc74cf1bb517651868342b0619b21eaaf9f94a2022c9c61886dd980e16fb091b"
    ;;
  Linux/x86_64|Linux/amd64)
    platform="x86_64-unknown-linux-gnu"
    expected_sha256="c218f50baeb2c06a30c2f03db5986b2bad6ab7c8a52faad2d5a59bda0677b93a"
    ;;
  *)
    echo "ERROR: unsupported platform '$(uname -s)/$(uname -m)'." >&2
    echo "This portable launcher supports current macOS and Linux systems." >&2
    exit 1
    ;;
esac

PYTHON_BIN="$PYTHON_DIR/install/bin/python3"
installed_version=""
if [ -x "$PYTHON_BIN" ]; then
  installed_version="$("$PYTHON_BIN" -c 'import platform; print(platform.python_version())' 2>/dev/null || true)"
fi

if [ "$installed_version" = "$PBS_PY_VERSION" ]; then
  echo "Bundled Python $installed_version is ready."
  exit 0
fi

archive_name="cpython-${PBS_PY_VERSION}+${PBS_RELEASE}-${platform}-install_only.tar.gz"
archive_url="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/${archive_name}"
archive_path="$DOWNLOADS_DIR/$archive_name"
mkdir -p "$DOWNLOADS_DIR"

if [ ! -f "$archive_path" ]; then
  echo "Downloading pinned Python ${PBS_PY_VERSION} for ${platform} ..."
  curl --fail --location --retry 3 --retry-delay 2 --progress-bar \
    -o "$archive_path.part" "$archive_url"
  mv "$archive_path.part" "$archive_path"
else
  echo "Using the cached Python runtime archive."
fi

if command -v shasum >/dev/null 2>&1; then
  actual_sha256="$(shasum -a 256 "$archive_path" | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then
  actual_sha256="$(sha256sum "$archive_path" | awk '{print $1}')"
else
  echo "ERROR: 'shasum' or 'sha256sum' is required to verify the runtime." >&2
  exit 1
fi

if [ "$actual_sha256" != "$expected_sha256" ]; then
  rm -f "$archive_path"
  echo "ERROR: the downloaded Python runtime failed SHA-256 verification." >&2
  exit 1
fi
echo "Verified the pinned Python runtime checksum."

rm -rf "$PYTHON_DIR"
mkdir -p "$PYTHON_DIR/install"
tar -xzf "$archive_path" -C "$PYTHON_DIR/install" --strip-components=1
if [ ! -x "$PYTHON_BIN" ]; then
  echo "ERROR: the downloaded Python archive did not contain $PYTHON_BIN." >&2
  exit 1
fi

if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$PYTHON_DIR" 2>/dev/null || true
fi
echo "Installed $("$PYTHON_BIN" --version 2>&1) at $PYTHON_BIN"
