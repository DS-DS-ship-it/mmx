#!/usr/bin/env bash
set -euo pipefail
OWNER="$(gh api user -q .login)"
TAP_REPO="${OWNER}/homebrew-mmx"
VER="${1:-v0.2.2}"
URL="https://github.com/${OWNER}/mmx/releases/download/${VER}/mmx-macos-universal.tar.gz"
SHA="$(curl -sL "https://github.com/${OWNER}/mmx/releases/download/${VER}/mmx-macos-universal.tar.gz.sha256" || true)"
test -n "$SHA" || { echo "missing sha256"; exit 1; }
tmpdir="$(mktemp -d)"
mkdir -p "$tmpdir/Formula"
cat > "$tmpdir/Formula/mmx.rb" <<RB
class Mmx < Formula
  desc "Media swiss-army CLI"
  homepage "https://github.com/${OWNER}/mmx"
  url "${URL}"
  sha256 "${SHA}"
  version "${VER#v}"
  def install
    bin.install "mmx"
  end
  test do
    system "#{bin}/mmx", "--help"
  end
end
RB
gh repo view "$TAP_REPO" >/dev/null 2>&1 || gh repo create "$TAP_REPO" --public -y
git -C "$tmpdir" init
git -C "$tmpdir" add -A
git -C "$tmpdir" commit -m "mmx ${VER}"
git -C "$tmpdir" branch -M main
git -C "$tmpdir" remote add origin "https://github.com/${TAP_REPO}.git"
git -C "$tmpdir" push -f origin main
echo "brew tap ${OWNER}/mmx && brew install mmx"
