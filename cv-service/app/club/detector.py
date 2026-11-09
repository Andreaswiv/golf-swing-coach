"""Golf club detection (shaft, club head, hands) with an ONNX model.

The model is SwingTrace's YOLO11m (https://github.com/nishsm/golf-club-detection-swingtrace,
AGPL-3.0, trained on the CC BY 4.0 "golf-club-tracking" dataset), converted to ONNX and
quantized to 8 bits when the Docker image is built (see the Dockerfile), so the service
needs ONNX Runtime but not PyTorch.

YOLO11 ONNX output: (1, 4 + classes, anchors) with box centre x, y, width, height in
input pixels, then one score per class. The analysis only needs the single most likely
shaft, head and hands per frame, so each class keeps its best-scoring box; no NMS needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# Model class index -> part. The source dataset labels them "0", "1" and "3".
PARTS = ("shaft", "head", "hands")
# YOLO input sides must be multiples of this.
STRIDE = 32


@dataclass
class Box:
    """Normalised to the full frame (0..1), with the model's confidence."""

    x1: float
    y1: float
    x2: float
    y2: float
    conf: float

    def to_list(self) -> list[float]:
        return [round(self.x1, 4), round(self.y1, 4), round(self.x2, 4), round(self.y2, 4), round(self.conf, 3)]


class ClubDetector:
    name = "club-detector"

    def detect(self, frame_bgr: np.ndarray) -> dict[str, Box]:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class OnnxClubDetector(ClubDetector):
    def __init__(self, model_path: Path, input_size: int = 640, min_conf: float = 0.35, threads: int = 0) -> None:
        import onnxruntime as ort  # imported lazily: tests use a fake detector

        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(f"Club model not found at {model_path}.")
        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self._session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        self._input = self._session.get_inputs()[0].name
        self.size = input_size
        self.min_conf = min_conf
        self.name = f"swingtrace-yolo11m-onnx:{model_path.stem}"

    def preprocess(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, float, float, float]:
        """Scale the longest side to ``size``, then pad with grey only up to a multiple of STRIDE.

        The input follows the frame's shape instead of a square: a portrait video keeps the same
        detail, and the model no longer spends 40% of its time on grey bars.
        """
        h, w = frame_bgr.shape[:2]
        scale = self.size / max(h, w)
        nh, nw = int(round(h * scale)), int(round(w * scale))
        height, width = -(-nh // STRIDE) * STRIDE, -(-nw // STRIDE) * STRIDE
        resized = cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        top, left = (height - nh) // 2, (width - nw) // 2
        canvas = np.full((height, width, 3), 114, dtype=np.uint8)
        canvas[top : top + nh, left : left + nw] = resized
        blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        return np.ascontiguousarray(blob), scale, left, top

    def decode(self, output: np.ndarray, scale: float, left: float, top: float, w: int, h: int) -> dict[str, Box]:
        pred = output[0]  # (4 + classes, anchors)
        boxes, scores = pred[:4], pred[4:]
        found: dict[str, Box] = {}
        for c, part in enumerate(PARTS[: scores.shape[0]]):
            i = int(np.argmax(scores[c]))
            conf = float(scores[c, i])
            if conf < self.min_conf:
                continue
            cx, cy, bw, bh = boxes[:, i]
            x1 = ((cx - bw / 2) - left) / scale
            y1 = ((cy - bh / 2) - top) / scale
            x2 = ((cx + bw / 2) - left) / scale
            y2 = ((cy + bh / 2) - top) / scale
            found[part] = Box(
                float(np.clip(x1 / w, 0, 1)),
                float(np.clip(y1 / h, 0, 1)),
                float(np.clip(x2 / w, 0, 1)),
                float(np.clip(y2 / h, 0, 1)),
                conf,
            )
        return found

    def detect(self, frame_bgr: np.ndarray) -> dict[str, Box]:
        h, w = frame_bgr.shape[:2]
        blob, scale, left, top = self.preprocess(frame_bgr)
        output = self._session.run(None, {self._input: blob})[0]
        return self.decode(output, scale, left, top, w, h)
