from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from .config import Settings


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}


class UploadValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedUpload:
    extension: str
    media_kind: str
    pages: int
    width: int | None = None
    height: int | None = None


def validate_upload(
    filename: str,
    content: bytes,
    mode: str,
    config: Settings,
) -> ValidatedUpload:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError("不支持的文件格式")
    if not content:
        raise UploadValidationError("上传文件为空")
    if len(content) > config.max_upload_bytes:
        raise UploadValidationError("文件超过 15MB 限制")

    page_limit = {
        "ocr": config.ocr_max_pages,
        "structure": config.structure_max_pages,
        "vl": config.vl_max_pages,
    }[mode]

    if extension == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise UploadValidationError("文件扩展名与 PDF 内容不匹配")
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = len(reader.pages)
        except Exception as exc:
            raise UploadValidationError("PDF 文件损坏或无法读取") from exc
        if pages < 1:
            raise UploadValidationError("PDF 没有可处理页面")
        if pages > page_limit:
            raise UploadValidationError(f"当前模式最多处理 {page_limit} 页 PDF")
        return ValidatedUpload(extension=".pdf", media_kind="pdf", pages=pages)

    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UploadValidationError("图片文件损坏或格式与扩展名不匹配") from exc

    if width * height > config.max_image_pixels:
        raise UploadValidationError("图片像素超过 2500 万限制")
    return ValidatedUpload(
        extension=extension,
        media_kind="image",
        pages=1,
        width=width,
        height=height,
    )

