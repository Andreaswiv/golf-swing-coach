"""HTTP-level tests. Skipped automatically when FastAPI is not installed."""

from __future__ import annotations

import importlib
import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POSE_MODEL_PATH", str(tmp_path / "missing.task"))
    from fastapi.testclient import TestClient

    import app.main as main

    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def test_health_reports_missing_model_as_degraded(client):
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["pose_model_present"] is False
    assert body["data_dir_present"] is True


def test_unknown_job_is_404(client):
    assert client.get("/jobs/nope").status_code == 404


def test_path_traversal_is_rejected(client):
    response = client.post(
        "/jobs",
        json={
            "analysis_id": "x",
            "video_path": "../../etc/passwd",
            "keypoints_path": "keypoints/x.json",
            "camera_angle": "face_on",
            "handedness": "right",
        },
    )
    assert response.status_code == 400


def test_invalid_camera_angle_is_422(client):
    response = client.post(
        "/jobs",
        json={
            "analysis_id": "x",
            "video_path": "videos/x.mp4",
            "keypoints_path": "keypoints/x.json",
            "camera_angle": "overhead",
            "handedness": "right",
        },
    )
    assert response.status_code == 422


def test_analyze_reruns_swing_analysis_from_a_keypoints_file(client, tmp_path):
    from .test_swing import make_payload

    (tmp_path / "keypoints").mkdir()
    (tmp_path / "keypoints" / "a.json").write_text(json.dumps(make_payload()))
    response = client.post("/analyze", json={"keypoints_path": "keypoints/a.json"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert [p["name"] for p in body["phases"]] == ["address", "takeaway", "top", "impact", "finish"]


def test_analyze_rejects_missing_and_escaping_paths(client):
    assert client.post("/analyze", json={"keypoints_path": "keypoints/none.json"}).status_code == 404
    assert client.post("/analyze", json={"keypoints_path": "../../etc/passwd"}).status_code == 400
