# Multi-arch: builds natively on Apple Silicon (linux/arm64) and on x86_64.
# MediaPipe publishes wheels for both; Python 3.12 is the safest common target.
FROM python:3.12-slim

# libgl1 / libglib2.0-0: required by opencv-contrib-python (pulled in by mediapipe).
# libegl1 / libgles2: the MediaPipe Tasks runtime loads them even when running on CPU.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libegl1 libgles2 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pose model (lite | full | heavy). "full" is a good CPU default; "heavy" is more
# accurate on fast motion but noticeably slower.
ARG POSE_MODEL_VARIANT=full
RUN mkdir -p /app/models \
    && curl -fsSL -o /app/models/pose_landmarker_${POSE_MODEL_VARIANT}.task \
       "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_${POSE_MODEL_VARIANT}/float16/latest/pose_landmarker_${POSE_MODEL_VARIANT}.task"
ENV POSE_MODEL_PATH=/app/models/pose_landmarker_${POSE_MODEL_VARIANT}.task \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1

COPY app ./app

# Smoke test: load the model and run one frame, so a missing native library fails
# the build instead of the first upload.
RUN python -c "import os, numpy as np; from pathlib import Path; \
from app.pose.mediapipe_estimator import MediaPipePoseEstimator; \
MediaPipePoseEstimator(Path(os.environ['POSE_MODEL_PATH'])).estimate(np.zeros((256, 256, 3), np.uint8), 0)"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
