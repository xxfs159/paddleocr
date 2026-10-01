from __future__ import annotations

import io
from html.parser import HTMLParser
from pathlib import Path

import pytest

from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import SAMPLES, _render_markdown, create_app
from app.manager import FakeJobManager


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


def test_security_headers_include_hardening(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/health")

    csp = response.headers["content-security-policy"]
    assert "object-src 'none'" in csp
    assert "base-uri 'none'" in csp
    assert "frame-ancestors 'none'" in csp


class ParsedHTML(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def url_attributes(markdown):
    return [attrs[attr]
            for tag, attrs in ParsedHTML(_render_markdown(markdown, "job")).elements
            for attr in ("href", "src") if attr in attrs]


@pytest.mark.parametrize("prefix", ["", "!"])
@pytest.mark.parametrize("url", [
    "data:image/png;base64,WA==", "DATA:image/png;base64,WA==",
    "data:text/html;base64,WA==", "javascript:alert(1)",
    "jav&#x61;script:alert(1)",
    "vbscript:msgbox(1)", "file:///etc/passwd", "ftp://example.com/a",
    "mailto:a@example.com",
])
def test_markdown_rejects_unsafe_urls(prefix, url):
    assert url_attributes(f"{prefix}[label]({url})") == []


@pytest.mark.parametrize("prefix", ["", "!"])
@pytest.mark.parametrize("url", [
    "http://example.com/a", "https://example.com/a", "//example.com/a",
    "/local", "../local", "#section",
])
def test_markdown_preserves_supported_urls(prefix, url):
    assert url_attributes(f"{prefix}[label]({url})") == [url]


def test_markdown_rewrites_local_image_only():
    assert url_attributes("![figure](markdown_assets/a.png)") == [
        "/api/jobs/job/artifacts/markdown_assets/a.png"]
    assert url_attributes("[download](markdown_assets/a.png)") == ["markdown_assets/a.png"]


@pytest.mark.parametrize("case,expected", [
    ("normal", 200), ("inside_absolute", 200), ("inside_link", 200),
    ("root", 404), ("root_absolute", 404), ("directory", 404),
    ("outside_relative", 404), ("outside_absolute", 404),
    ("sibling", 404), ("outside_link", 404), ("outside_directory_link", 404),
    ("missing", 404), ("broken_link", 404), ("loop", 404),
])
def test_sample_file_boundaries(tmp_path, monkeypatch, case, expected):
    root = tmp_path / "root"
    root.mkdir()
    (root / "ok.txt").write_text("inside", encoding="utf-8")
    (root / "directory").mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    sibling = tmp_path / "root-sibling"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("secret", encoding="utf-8")
    paths = {
        "normal": "ok.txt", "inside_absolute": str(root / "ok.txt"),
        "root": ".", "root_absolute": str(root), "directory": "directory",
        "outside_relative": "../secret.txt", "outside_absolute": str(outside),
        "sibling": "../root-sibling/secret.txt", "missing": "missing",
    }
    links = {
        "inside_link": root / "ok.txt", "outside_link": outside,
        "outside_directory_link": sibling, "broken_link": tmp_path / "missing",
        "loop": root / "loop",
    }
    if case in links:
        (root / case).symlink_to(links[case], target_is_directory=case == "outside_directory_link")
        paths[case] = case + ("/secret.txt" if case == "outside_directory_link" else "")
    monkeypatch.setitem(SAMPLES, "ocr", {"name": "sample", "path": paths[case]})
    with make_client(root) as client:
        response = client.get("/api/samples/ocr")
    assert response.status_code == expected
    if expected == 200:
        assert response.content == b"inside"
    else:
        assert response.json() == {"detail": "本地 PaddleOCR 示例文件不存在"}


@pytest.mark.parametrize("sample_id", ["unknown", "%2e%2e%2fsecret.txt", "%2Fetc%2Fpasswd", "..%5Csecret.txt"])
def test_sample_id_is_not_a_file_path(tmp_path, sample_id):
    with make_client(tmp_path) as client:
        assert client.get(f"/api/samples/{sample_id}").status_code == 404


def test_sample_root_symlink(tmp_path, monkeypatch):
    root = tmp_path / "real"
    root.mkdir()
    (root / "ok.txt").write_text("inside", encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    monkeypatch.setitem(SAMPLES, "ocr", {"name": "sample", "path": "ok.txt"})
    with make_client(alias) as client:
        response = client.get("/api/samples/ocr")
    assert response.status_code == 200
    assert response.content == b"inside"


@pytest.mark.parametrize("error", [PermissionError("denied"), RuntimeError("symlink loop")])
def test_sample_resolution_errors_are_hidden(tmp_path, monkeypatch, error):
    with make_client(tmp_path) as client:
        def fail_resolve(self, *args, **kwargs):
            raise error
        monkeypatch.setattr(Path, "resolve", fail_resolve)
        response = client.get("/api/samples/ocr")
    assert response.status_code == 404
    assert response.json() == {"detail": "本地 PaddleOCR 示例文件不存在"}


@pytest.mark.parametrize("prefix", ["", "!"])
def test_markdown_percent_encodes_embedded_tab(prefix):
    # MarkdownIt encodes the tab: this is a relative URL, not a javascript scheme.
    assert url_attributes(f"{prefix}[label](java&#x09;script:alert(1))") == [
        "java%09script:alert(1)"
    ]
