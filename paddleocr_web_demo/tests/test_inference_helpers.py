import json

from PIL import Image

from paddleocr.paddleocr_web_demo.app.inference import (
    _extract_document_page,
    _extract_ocr_page,
    json_safe,
    run_inference,
)


class ArrayLike:
    def tolist(self):
        return [[1, 2], [3, 4]]


def test_json_safe_converts_array_like():
    assert json_safe({"array": ArrayLike()}) == {"array": [[1, 2], [3, 4]]}


def test_extract_ocr_page():
    page = {
        "res": {
            "rec_texts": ["你好"],
            "rec_scores": [0.98],
            "rec_polys": [[[0, 0], [10, 0], [10, 10], [0, 10]]],
        }
    }
    summary = _extract_ocr_page(page, 0)
    assert summary["line_count"] == 1
    assert summary["lines"][0]["text"] == "你好"


def test_extract_document_page():
    page = {
        "res": {
            "parsing_res_list": [
                {
                    "block_label": "table",
                    "block_content": "| A |",
                    "block_bbox": [0, 0, 10, 10],
                }
            ]
        }
    }
    summary = _extract_document_page(page, 0)
    assert summary["block_count"] == 1
    assert summary["blocks"][0]["label"] == "table"


class FakeResult:
    json = {
        "res": {
            "rec_texts": ["hello"],
            "rec_scores": [0.99],
            "rec_polys": [[[0, 0], [5, 0], [5, 5], [0, 5]]],
        }
    }
    img = {"ocr_res_img": Image.new("RGB", (10, 10), "white")}


class FakePipeline:
    def predict(self, _):
        return [FakeResult()]


def test_run_inference_writes_artifacts(tmp_path):
    phases = []
    result = run_inference(
        FakePipeline(),
        "ocr",
        "sample.png",
        str(tmp_path),
        lambda phase, progress: phases.append((phase, progress)),
    )
    assert result["item_count"] == 1
    assert "result.json" in result["artifacts"]
    assert any(name.startswith("visuals/") for name in result["artifacts"])
    saved = json.loads((tmp_path / "artifacts" / "result.json").read_text())
    assert saved["pages"][0]["res"]["rec_texts"] == ["hello"]
    assert phases[-1][1] == 95
