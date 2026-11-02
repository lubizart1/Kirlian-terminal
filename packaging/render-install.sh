#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Write dist/install.sh for the wheel built in dist/: the release's version and checksum.
# Usage: packaging/render-install.sh   (after `uv build`)
set -eu
cd "$(dirname "$0")/.."
version=$(uv version --short)
wheel="dist/kirlian_terminal-$version-py3-none-any.whl"
[ -f "$wheel" ] || { echo "Build first: $wheel is missing" >&2; exit 1; }
if command -v sha256sum >/dev/null 2>&1; then
    sha=$(sha256sum "$wheel" | cut -d' ' -f1)
else
    sha=$(shasum -a 256 "$wheel" | cut -d' ' -f1)
fi
sed -e "s/@VERSION@/$version/" -e "s/@SHA256@/$sha/" packaging/install.sh > dist/install.sh
chmod +x dist/install.sh
echo "dist/install.sh: version $version, wheel sha256 $sha"
