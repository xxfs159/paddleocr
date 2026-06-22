from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("PADDLE_DEMO_DATA_DIR", BASE_DIR / "data"))
    paddleocr_dir: Path = Path(os.getenv("PADDLEOCR_DIR", "/home/lyc/PaddleOCR"))
    max_upload_bytes: int = 15 * 1024 * 1024
    max_image_pixels: int = 25_000_000
    max_waiting_jobs: int = 3
    rate_limit_requests: int = 5
    rate_limit_window_seconds: int = 10 * 60
    result_ttl_seconds: int = 30 * 60
    ocr_max_pages: int = 10
    structure_max_pages: int = 10
    vl_max_pages: int = 3
    worker_start_timeout: int = int(os.getenv("PADDLE_DEMO_MODEL_TIMEOUT", "1800"))
    job_timeout: int = int(os.getenv("PADDLE_DEMO_JOB_TIMEOUT", "1800"))

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"


settings = Settings()
