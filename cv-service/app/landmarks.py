"""MediaPipe Pose landmark definitions (33 landmarks)."""

LANDMARK_NAMES: list[str] = [
    "nose",
    "left_eye_inner",
    "left_eye",
    "left_eye_outer",
    "right_eye_inner",
    "right_eye",
    "right_eye_outer",
    "left_ear",
    "right_ear",
    "mouth_left",
    "mouth_right",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_pinky",
    "right_pinky",
    "left_index",
    "right_index",
    "left_thumb",
    "right_thumb",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
]

LANDMARK_INDEX: dict[str, int] = {name: i for i, name in enumerate(LANDMARK_NAMES)}

# Per-landmark values stored for every frame.
LANDMARK_FIELDS: list[str] = ["x", "y", "z", "visibility", "presence"]

# Joints the swing analysis depends on; used by the quality checks.
KEY_JOINTS: list[str] = [
    "left_shoulder",
    "right_shoulder",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
]

# If these leave the frame, the golfer is not fully visible.
FRAME_EDGE_LANDMARKS: list[str] = [
    "nose",
    "left_ankle",
    "right_ankle",
    "left_wrist",
    "right_wrist",
]
