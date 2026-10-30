#!/usr/bin/env bash
# Download the MediaPipe pose model for running the CV service OUTSIDE Docker.
# (The Docker image downloads it itself at build time.)
#
# Usage: scripts/download_pose_model.sh [lite|full|heavy]
set -euo pipefail

VARIANT="${1:-full}"
case "$VARIANT" in lite|full|heavy) ;; *) echo "Variant must be lite, full or heavy." >&2; exit 2 ;; esac

DEST_DIR="$(cd "$(dirname "$0")/.." && pwd)/cv-service/models"
DEST="$DEST_DIR/pose_landmarker_${VARIANT}.task"
URL="https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_${VARIANT}/float16/latest/pose_landmarker_${VARIANT}.task"

mkdir -p "$DEST_DIR"
echo "Downloading $VARIANT pose model to $DEST"
curl -fL --progress-bar -o "$DEST.tmp" "$URL"
mv "$DEST.tmp" "$DEST"
echo "Done. Run the CV service with:"
echo "  POSE_MODEL_PATH=$DEST DATA_DIR=$(cd "$DEST_DIR/../.." && pwd)/data uvicorn app.main:app --port 8000"
