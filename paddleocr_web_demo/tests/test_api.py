from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from paddleocr.paddleocr_web_demo.app.config import Settings
from paddleocr.paddleocr_web_demo.app.main import _render_markdown, create_app
from paddleocr.paddleocr_web_demo.app.manager import FakeJobManager


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def make_client(tmp_path) -> TestClient:
    config = Settings(data_dir=tmp_path, paddleocr_dir=tmp_path)
    return TestClient(create_app(FakeJobManager(), config))


def test_health(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_create_and_get_job(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/jobs",
            data={"mode": "ocr"},
            files={"file": ("sample.png", png_bytes(), "image/png")},
        )
        assert response.status_code == 202
        job_id = response.json()["id"]
        status = client.get(f"/api/jobs/{job_id}")
        assert status.status_code == 200
        assert status.json()["mode"] == "ocr"


def test_rejects_bad_mode_and_file(tmp_path):
    with make_client(tmp_path) as client:
        bad_mode = client.post(
            "/api/jobs",
            data={"mode": "unknown"},
            files={"file": ("sample.png", png_bytes(), "image/png")},
        )
        assert bad_mode.status_code == 422
        bad_file = client.post(
            "/api/jobs",
            data={"mode": "ocr"},
            files={"file": ("sample.txt", b"hello", "text/plain")},
        )
        assert bad_file.status_code == 422


def test_delete_job(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/jobs",
            data={"mode": "ocr"},
            files={"file": ("sample.png", png_bytes(), "image/png")},
        )
        job_id = response.json()["id"]
        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_markdown_disables_raw_html():
    rendered = _render_markdown("<script>alert(1)</script>\n\n# Safe", "job")
    assert "<script>" not in rendered
    assert "<h1>Safe</h1>" in rendered


def test_markdown_disables_data_links():
    rendered = _render_markdown('[x](data:text/html;base64,PHNjcmlwdD4=)', "job")
    assert "href=" not in rendered


def test_security_headers_include_hardening(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/health")
        csp = response.headers["content-security-policy"]
        assert "object-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp
