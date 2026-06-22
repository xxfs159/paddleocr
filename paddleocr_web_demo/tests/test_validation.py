from __future__ import annotations

import io

import pytest
from PIL import Image

from paddleocr.paddleocr_web_demo.app.config import Settings
from paddleocr.paddleocr_web_demo.app.validation import UploadValidationError, validate_upload


def image_bytes(size: tuple[int, int] = (100, 80), fmt: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=fmt)
    return buffer.getvalue()


def test_valid_image(tmp_path):
    config = Settings(data_dir=tmp_path)
    result = validate_upload("sample.png", image_bytes(), "ocr", config)
    assert result.media_kind == "image"
    assert result.width == 100
    assert result.height == 80


def test_rejects_extension_content_mismatch(tmp_path):
    config = Settings(data_dir=tmp_path)
    with pytest.raises(UploadValidationError):
        validate_upload("fake.pdf", image_bytes(), "structure", config)


def test_rejects_large_pixel_count(tmp_path):
    config = Settings(data_dir=tmp_path, max_image_pixels=100)
    with pytest.raises(UploadValidationError, match="像素"):
        validate_upload("large.png", image_bytes((20, 20)), "ocr", config)


def test_rejects_unsupported_extension(tmp_path):
    config = Settings(data_dir=tmp_path)
    with pytest.raises(UploadValidationError, match="格式"):
        validate_upload("notes.txt", b"hello", "ocr", config)

