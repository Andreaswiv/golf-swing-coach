"""Quantize the club detection model to 8-bit weights. Runs during the Docker build.

About 3x smaller and 2-5x faster on a CPU (most of all inside Docker on a Mac, where floating-point
inference is unusually slow). The box and class outputs (the Detect head, layer 23) stay in floating
point: quantizing them costs accuracy and saves little.

Calibration only needs ordinary photos to learn the value ranges inside the network, so it uses the
two sample photos that ship with Ultralytics, varied in crop, mirroring, brightness and orientation.
No golfer's video is needed, and on a real swing the result matched the floating-point model
(typically under 1 px; see DEVELOPMENT_STATUS.md).

Usage: quantize_club_model.py <input.onnx> <output.onnx>
"""

from __future__ import annotations

import sys

import cv2
import numpy as np
import onnx
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from ultralytics.utils import ASSETS

VARIATIONS_PER_PHOTO = 24
DETECT_HEAD = "model.23"


def calibration_inputs():
    rng = np.random.default_rng(0)  # the same model on every build
    for path in sorted(ASSETS.glob("*.jpg")):
        image = cv2.imread(str(path))
        h, w = image.shape[:2]
        for k in range(VARIATIONS_PER_PHOTO):
            keep = rng.uniform(0.5, 1.0)
            crop_h, crop_w = int(h * keep), int(w * keep)
            y, x = rng.integers(0, h - crop_h + 1), rng.integers(0, w - crop_w + 1)
            crop = image[y : y + crop_h, x : x + crop_w]
            if k % 2:
                crop = crop[:, ::-1]
            crop = np.clip(crop.astype(np.float32) * rng.uniform(0.5, 1.4), 0, 255).astype(np.uint8)
            height, width = (640, 384) if k % 3 else (384, 640)  # mostly portrait, like phone videos
            crop = cv2.resize(crop, (width, height))
            yield np.ascontiguousarray(crop[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0)


class Photos(CalibrationDataReader):
    def __init__(self, input_name: str) -> None:
        self._name = input_name
        self._inputs = calibration_inputs()

    def get_next(self) -> dict | None:
        blob = next(self._inputs, None)
        return None if blob is None else {self._name: blob}


def main(source: str, target: str) -> None:
    graph = onnx.load(source).graph
    quantize_static(
        source,
        target,
        Photos(graph.input[0].name),
        quant_format=QuantFormat.QDQ,
        per_channel=True,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QUInt8,
        nodes_to_exclude=[node.name for node in graph.node if DETECT_HEAD in node.name],
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
