#!/usr/bin/env bash
# Assemble a Hugging Face Docker Space repository (backend only, no binaries).
# Usage: deploy/huggingface/build-space.sh <output-dir>
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
out="${1:?output directory required}"
rm -rf "$out"
mkdir -p "$out"
# Free Spaces use the Gradio SDK runtime: it installs requirements.txt and runs
# space_main.py, which serves the FastAPI app on port 7860 (the Dockerfile is the
# paid Docker-Space path).
cp "$root/deploy/huggingface/README.md" "$root/deploy/huggingface/space_main.py" \
  "$root/deploy/huggingface/requirements.txt" "$out/"
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
