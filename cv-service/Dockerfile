# Multi-arch: builds natively on Apple Silicon (linux/arm64) and on x86_64.
# MediaPipe publishes wheels for both; Python 3.12 is the safest common target.

# ---- Stage 1: club detection model -> ONNX ---------------------------------------------------
# SwingTrace YOLO11m (AGPL-3.0, https://github.com/nishsm/golf-club-detection-swingtrace), pinned
# to a commit and checked against a SHA-256 before it is loaded (.pt files are pickles). The
# weights were inspected: they only reference PyTorch and Ultralytics model classes.
# Converted to ONNX here so the service needs ONNX Runtime, not PyTorch (this stage is discarded).
FROM python:3.12-slim AS club-model
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir "ultralytics==8.3.253" "onnx==1.23.2" "onnxslim==0.1.98"
ARG CLUB_MODEL_COMMIT=3985bce45b9a4827d6ab1f7e8aeaeaa032ef6cd0
ARG CLUB_MODEL_SHA256=fcda5469a9cede0d4745d15dc797cd2ebcca4bda8b4e7e717b0b8c00a56d8744
WORKDIR /build
RUN curl -fsSL -o best.pt \
       "https://raw.githubusercontent.com/nishsm/golf-club-detection-swingtrace/${CLUB_MODEL_COMMIT}/weights/best.pt" \
    && echo "${CLUB_MODEL_SHA256}  best.pt" | sha256sum -c - \
    && YOLO_CONFIG_DIR=/tmp/yolo YOLO_OFFLINE=1 python -c \
       "from ultralytics import YOLO; YOLO('best.pt').export(format='onnx', imgsz=640, simplify=True)" \
    && mv best.onnx club_swingtrace_yolo11m.onnx

# ---- Stage 2: the service ------------------------------------------------------------------
FROM python:3.12-slim

# libgl1 / libglib2.0-0: required by opencv-contrib-python (pulled in by mediapipe).
# libegl1 / libgles2: the MediaPipe Tasks runtime loads them even when running on CPU.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libegl1 libgles2 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pose model (lite | full | heavy). "heavy": about 2.7x slower per frame than "full" (70 vs 26 ms
# on an M-series Mac), but from down-the-line it keeps the arms apart at the top of the swing and
# places the trail elbow where it is; "full" swapped left and right arm there.
ARG POSE_MODEL_VARIANT=heavy
RUN mkdir -p /app/models \
    && curl -fsSL -o /app/models/pose_landmarker_${POSE_MODEL_VARIANT}.task \
       "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_${POSE_MODEL_VARIANT}/float16/latest/pose_landmarker_${POSE_MODEL_VARIANT}.task"
COPY --from=club-model /build/club_swingtrace_yolo11m.onnx /app/models/
ENV POSE_MODEL_PATH=/app/models/pose_landmarker_${POSE_MODEL_VARIANT}.task \
    CLUB_MODEL_PATH=/app/models/club_swingtrace_yolo11m.onnx \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1

COPY app ./app

# Smoke test: load both models and run one frame, so a missing native library fails
# the build instead of the first upload.
RUN python -c "import os, numpy as np; from pathlib import Path; \
from app.pose.mediapipe_estimator import MediaPipePoseEstimator; \
from app.club.detector import OnnxClubDetector; \
MediaPipePoseEstimator(Path(os.environ['POSE_MODEL_PATH'])).estimate(np.zeros((256, 256, 3), np.uint8), 0); \
OnnxClubDetector(Path(os.environ['CLUB_MODEL_PATH'])).detect(np.zeros((256, 256, 3), np.uint8))"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
