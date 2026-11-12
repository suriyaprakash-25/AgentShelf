#!/usr/bin/env bash
# Assemble a Hugging Face Docker Space repository (backend only, no binaries).
# Usage: deploy/huggingface/build-space.sh <output-dir>
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
out="${1:?output directory required}"
rm -rf "$out"
mkdir -p "$out"
cp "$root/deploy/huggingface/Dockerfile" "$root/deploy/huggingface/start.sh" \
  "$root/deploy/huggingface/README.md" "$out/"
cp -r "$root/seed" "$out/seed"
mkdir -p "$out/backend"
(cd "$root/backend" && git ls-files -- . ':!:tests' | while read -r f; do
  mkdir -p "$out/backend/$(dirname "$f")"
  cp "$f" "$out/backend/$f"
done)
cd "$out"
git init -q -b main
git config core.autocrlf false
git add -A
git -c user.name="AgentShelf deploy" -c user.email="deploy@agentshelf.invalid" \
  commit -q -m "AgentShelf API Space"
echo "Space repository ready in $out"
