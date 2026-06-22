from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image


ProgressCallback = Callable[[str, int], None]


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    return str(value)


def create_pipeline(mode: str) -> Any:
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    if mode == "ocr":
        from paddleocr import PaddleOCR

        return PaddleOCR(
            device="gpu",
            text_detection_model_name="PP-OCRv6_medium_det",
            text_recognition_model_name="PP-OCRv6_medium_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    if mode == "structure":
        from paddleocr import PPStructureV3

        return PPStructureV3(
            device="gpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            use_table_recognition=True,
            use_formula_recognition=True,
        )
    if mode == "vl":
        from paddleocr import PaddleOCRVL

        return PaddleOCRVL(
            device="gpu",
            pipeline_version="v1.6",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_layout_detection=True,
        )
    raise ValueError(f"Unsupported mode: {mode}")


def _save_image(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if image.mode not in {"RGB", "RGBA", "L"}:
        image = image.convert("RGB")
    image.save(path)


def _safe_asset_name(raw_name: str, index: int) -> str:
    name = Path(raw_name).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or f"asset_{index:03d}.png"


def _extract_ocr_page(page: dict[str, Any], page_index: int) -> dict[str, Any]:
    body = page.get("res", page)
    texts = body.get("rec_texts", [])
    scores = body.get("rec_scores", [])
    polygons = body.get("rec_polys", body.get("dt_polys", []))
    lines = []
    for index, text in enumerate(texts):
        lines.append(
            {
                "text": str(text),
                "score": float(scores[index]) if index < len(scores) else None,
                "polygon": json_safe(polygons[index]) if index < len(polygons) else None,
            }
        )
    return {"page": page_index + 1, "lines": lines, "line_count": len(lines)}


def _extract_document_page(page: dict[str, Any], page_index: int) -> dict[str, Any]:
    body = page.get("res", page)
    blocks = []
    for block in body.get("parsing_res_list", [])[:200]:
        blocks.append(
            {
                "label": block.get("block_label", "unknown"),
                "content": str(block.get("block_content", "")),
                "bbox": json_safe(block.get("block_bbox")),
                "order": block.get("block_order"),
            }
        )
    if not blocks:
        layout = body.get("layout_det_res", {})
        for block in layout.get("boxes", [])[:200]:
            blocks.append(
                {
                    "label": block.get("label", "unknown"),
                    "content": str(block.get("content", "")),
                    "bbox": json_safe(block.get("coordinate")),
                    "score": block.get("score"),
                }
            )
    return {"page": page_index + 1, "blocks": blocks, "block_count": len(blocks)}


def run_inference(
    pipeline: Any,
    mode: str,
    input_path: str,
    job_dir: str,
    progress: ProgressCallback,
) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(job_dir)
    artifact_dir = root / "artifacts"
    visual_dir = artifact_dir / "visuals"
    markdown_asset_dir = artifact_dir / "markdown_assets"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    progress("执行模型推理", 35)
    outputs = list(pipeline.predict(input_path))
    if not outputs:
        raise RuntimeError("模型没有返回识别结果")

    progress("整理结构化结果", 70)
    raw_pages: list[dict[str, Any]] = []
    summary_pages: list[dict[str, Any]] = []
    markdown_items: list[dict[str, Any]] = []

    for page_index, result in enumerate(outputs):
        page_json = json_safe(result.json)
        raw_pages.append(page_json)
        if mode == "ocr":
            summary_pages.append(_extract_ocr_page(page_json, page_index))
        else:
            summary_pages.append(_extract_document_page(page_json, page_index))

        try:
            for key, image in result.img.items():
                if isinstance(image, Image.Image):
                    filename = f"page_{page_index + 1:03d}_{_safe_asset_name(str(key), 0)}.png"
                    _save_image(image, visual_dir / filename)
        except Exception:
            pass

        if mode != "ocr":
            try:
                markdown_info = result.markdown
                markdown_items.append(markdown_info)
                for asset_index, (raw_name, image) in enumerate(
                    markdown_info.get("markdown_images", {}).items()
                ):
                    if not isinstance(image, Image.Image):
                        continue
                    filename = _safe_asset_name(str(raw_name), asset_index)
                    _save_image(image, markdown_asset_dir / filename)
                    markdown_info["markdown_texts"] = markdown_info.get(
                        "markdown_texts", ""
                    ).replace(str(raw_name), f"markdown_assets/{filename}")
            except Exception:
                pass

            try:
                result.save_to_word(
                    save_path=str(artifact_dir / f"page_{page_index + 1:03d}.docx")
                )
            except Exception:
                pass

    aggregate = {
        "mode": mode,
        "input_name": Path(input_path).name,
        "page_count": len(outputs),
        "pages": raw_pages,
    }
    (artifact_dir / "result.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown_text = ""
    if markdown_items:
        try:
            markdown_text = pipeline.concatenate_markdown_pages(markdown_items)
            if isinstance(markdown_text, tuple):
                markdown_text = markdown_text[0]
        except Exception:
            markdown_text = "\n\n---\n\n".join(
                str(item.get("markdown_texts", "")) for item in markdown_items
            )
        (artifact_dir / "result.md").write_text(
            str(markdown_text), encoding="utf-8"
        )

    artifacts = []
    for path in sorted(artifact_dir.rglob("*")):
        if path.is_file():
            artifacts.append(path.relative_to(artifact_dir).as_posix())

    elapsed = round(time.perf_counter() - started, 3)
    if mode == "ocr":
        item_count = sum(page["line_count"] for page in summary_pages)
    else:
        item_count = sum(page["block_count"] for page in summary_pages)

    result_manifest = {
        "mode": mode,
        "page_count": len(outputs),
        "item_count": item_count,
        "elapsed_seconds": elapsed,
        "pages": summary_pages,
        "markdown": str(markdown_text),
        "artifacts": artifacts,
    }
    (root / "manifest.json").write_text(
        json.dumps(result_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    progress("生成预览与下载文件", 95)
    return result_manifest
