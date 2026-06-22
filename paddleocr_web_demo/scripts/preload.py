from __future__ import annotations

import argparse
import gc
import shutil
import tempfile
from pathlib import Path

from paddleocr.paddleocr_web_demo.app.inference import create_pipeline, run_inference


SAMPLES = {
    "ocr": "deploy/ios_demo/PaddleOCRDemo/Resources/SampleImages/general_ocr_002.jpg",
    "structure": "tests/test_files/medal_table.png",
    "vl": "tests/test_files/doc_with_formula.png",
}


def release_gpu() -> None:
    gc.collect()
    try:
        import paddle

        paddle.device.cuda.empty_cache()
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and warm PaddleOCR demo models")
    parser.add_argument(
        "--mode",
        choices=["all", *SAMPLES],
        default="all",
        help="Only preload one demo mode",
    )
    parser.add_argument(
        "--paddleocr-dir",
        default="/home/lyc/PaddleOCR",
        help="Path to the PaddleOCR source repository",
    )
    args = parser.parse_args()

    root = Path(args.paddleocr_dir).resolve()
    modes = list(SAMPLES) if args.mode == "all" else [args.mode]
    for mode in modes:
        sample = root / SAMPLES[mode]
        if not sample.is_file():
            raise SystemExit(f"Sample file not found: {sample}")
        temp_dir = Path(tempfile.mkdtemp(prefix=f"paddleocr-preload-{mode}-"))
        print(f"\n[{mode}] loading model and running {sample.name}")
        pipeline = create_pipeline(mode)
        result = run_inference(
            pipeline,
            mode,
            str(sample),
            str(temp_dir),
            lambda phase, progress: print(f"[{mode}] {progress:3d}% {phase}"),
        )
        print(
            f"[{mode}] ready: {result['page_count']} page(s), "
            f"{result['elapsed_seconds']} seconds"
        )
        del pipeline
        shutil.rmtree(temp_dir, ignore_errors=True)
        release_gpu()


if __name__ == "__main__":
    main()

