#!/bin/zsh
set -euo pipefail

TAG="v1.0.0"
OWNER="$(gh api user -q .login)"
REPO="mmx"

ASSET1="dist/mmx-macos-universal.tar.gz"
ASSET2="dist/mmx-sdk.tar.gz"

sum() { shasum -a 256 "$1" | awk '{print $1}'; }

if ! gh release view "$TAG" >/dev/null 2>&1; then
  gh release create "$TAG" -t "MMX Open Core $TAG" -n "Initial Open-Core release"
fi

for A in "$ASSET1" "$ASSET2"; do
  if [[ -f "$A" ]]; then
    if ! gh release view "$TAG" --json assets -q '.assets[].name' | grep -qx "$(basename "$A")"; then
      gh release upload "$TAG" "$A" --clobber
    fi
  fi
done

U_SUM=$(sum "$ASSET1")
S_SUM=$(sum "$ASSET2")

NOTES_FILE=$(mktemp)
cat >"$NOTES_FILE" <<EOF
## MMX Open Core $TAG

**Downloads**
- macOS Universal: \`$(basename "$ASSET1")\`
  \`SHA256: $U_SUM\`
- SDK bundle: \`$(basename "$ASSET2")\`
  \`SHA256: $S_SUM\`

**Install (macOS Universal)**
\`\`\`bash
tar -xzf $(basename "$ASSET1")
./mmx-macos-universal/mmx --help
\`\`\`

**SDK**
\`\`\`bash
tar -xzf $(basename "$ASSET2")
ls mmx-cli mmx-core
\`\`\`
EOF

gh release edit "$TAG" --notes-file "$NOTES_FILE"
rm -f "$NOTES_FILE"

gh repo edit "$OWNER/$REPO" \
  --enable-issues=true \
  --enable-discussions=true \
  --enable-wiki=false \
  --enable-projects=false \
  --homepage "https://github.com/$OWNER/$REPO" \
  --add-topic "video,encoding,transcoding,ffmpeg,media,cli,rust"

echo "https://github.com/$OWNER/$REPO/releases/tag/$TAG"
