#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Install or update Kirlian Terminal:
#   curl -fsSL https://github.com/lubizart1/Kirlian-terminal/releases/latest/download/install.sh | sh
#
# The release workflow fills in VERSION and SHA256 for the wheel attached to the
# same release. The script installs uv if needed, mpv with Homebrew on macOS, and
# then the `kirlian` command with `uv tool install`. It never uses sudo; on Linux it
# prints the package command for mpv instead. Run it again to update.
# For testing a local build: KIRLIAN_WHEEL=/path/to/kirlian_terminal-X-py3-none-any.whl
set -eu

VERSION="@VERSION@"
SHA256="@SHA256@"
REPOSITORY="lubizart1/Kirlian-terminal"
PYTHON_VERSION="3.13"

say() { printf '%s\n' "$*"; }
fail() {
    printf 'kirlian install: %s\n' "$*" >&2
    exit 1
}
has() { command -v "$1" >/dev/null 2>&1; }

case "$(uname -s)" in
    Darwin) os=macos ;;
    Linux) os=linux ;;
    *) fail "only macOS and Linux are supported." ;;
esac
has curl || fail "curl is required."

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT INT TERM

# 1. The playback engine.
if ! has mpv; then
    if [ "$os" = macos ] && has brew; then
        say "Installing mpv, the playback engine, with Homebrew..."
        brew install mpv
    elif [ "$os" = macos ]; then
        fail "mpv is required. Install Homebrew (https://brew.sh), then run: brew install mpv. Run this installer again afterwards."
    else
        if has apt-get; then hint="sudo apt-get install mpv"
        elif has dnf; then hint="sudo dnf install mpv"
        elif has pacman; then hint="sudo pacman -S mpv"
        elif has zypper; then hint="sudo zypper install mpv"
        else hint="install mpv with your package manager"
        fi
        fail "mpv is required. Run: $hint. Run this installer again afterwards."
    fi
fi

# 2. uv, which installs Python and the app in its own environment.
if ! has uv; then
    for dir in "${XDG_BIN_HOME:-}" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -n "$dir" ] && [ -x "$dir/uv" ]; then
            PATH="$dir:$PATH"
            break
        fi
    done
fi
if ! has uv; then
    say "Installing uv (https://docs.astral.sh/uv/)..."
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null
    PATH="$HOME/.local/bin:$PATH"
    has uv || fail "uv was installed but cannot be found; open a new terminal and run this again."
fi

# 3. Kirlian Terminal itself, checked against the release checksum.
if [ -n "${KIRLIAN_WHEEL:-}" ]; then
    wheel="$KIRLIAN_WHEEL"
    [ -f "$wheel" ] || fail "KIRLIAN_WHEEL does not point to a file: $wheel"
else
    case "$VERSION" in
        @*) fail "this is the unreleased template; download install.sh from a release." ;;
    esac
    wheel="$workdir/kirlian_terminal-$VERSION-py3-none-any.whl"
    say "Downloading Kirlian Terminal $VERSION..."
    curl -fsSL -o "$wheel" \
        "https://github.com/$REPOSITORY/releases/download/v$VERSION/kirlian_terminal-$VERSION-py3-none-any.whl" ||
        fail "could not download version $VERSION."
    if has sha256sum; then
        actual=$(sha256sum "$wheel" | cut -d' ' -f1)
    else
        actual=$(shasum -a 256 "$wheel" | cut -d' ' -f1)
    fi
    [ "$actual" = "$SHA256" ] || fail "the download does not match the published checksum; nothing was installed."
fi

say "Installing the kirlian command..."
uv tool install --quiet --force --python "$PYTHON_VERSION" "$wheel" ||
    fail "uv could not install Kirlian Terminal."

bin_dir=$(uv tool dir --bin)
say ""
say "Kirlian Terminal is installed: $bin_dir/kirlian"
case ":$PATH:" in
    *":$bin_dir:"*) say "Start it with: kirlian" ;;
    *)
        say "$bin_dir is not on your PATH yet. Run: uv tool update-shell"
        say "then open a new terminal and start it with: kirlian"
        ;;
esac
say "Update: run this installer again. Uninstall: uv tool uninstall kirlian-terminal"
