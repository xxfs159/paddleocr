from __future__ import annotations

import mimetypes
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import bleach
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt

from .config import BASE_DIR, Settings, settings
from .manager import JobManager, QueueFullError
from .rate_limit import SlidingWindowRateLimiter
from .schemas import VALID_MODES
from .validation import UploadValidationError, validate_upload


SAMPLES = {
    "ocr": {
        "name": "登机牌 OCR",
        "path": "deploy/ios_demo/PaddleOCRDemo/Resources/SampleImages/general_ocr_002.jpg",
    },
    "structure": {"name": "表格文档", "path": "tests/test_files/medal_table.png"},
    "vl": {"name": "公式文档", "path": "tests/test_files/doc_with_formula.png"},
}

ALLOWED_MARKDOWN_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


def _gpu_info() -> dict[str, Any]:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,driver_version",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=3,
        ).strip()
        name, total, used, driver = [item.strip() for item in output.splitlines()[0].split(",")]
        return {
            "available": True,
            "name": name,
            "memory_total_mb": int(total),
            "memory_used_mb": int(used),
            "driver": driver,
        }
    except Exception:
        return {"available": False}


def _render_markdown(text: str, job_id: str) -> str:
    renderer = MarkdownIt("commonmark", {"html": False, "linkify": False})
    html = renderer.render(text)
    clean = bleach.clean(
        html,
        tags=ALLOWED_MARKDOWN_TAGS,
        attributes={"a": ["href", "title"], "img": ["src", "alt", "title"]},
        protocols={"http", "https"},
        strip=True,
    )
    return clean.replace(
        'src="markdown_assets/',
        f'src="/api/jobs/{job_id}/artifacts/markdown_assets/',
    )


def create_app(
    job_manager: JobManager | None = None,
    config: Settings = settings,
) -> FastAPI:
    manager = job_manager or JobManager(config)
    limiter = SlidingWindowRateLimiter(
        config.rate_limit_requests, config.rate_limit_window_seconds
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await manager.start()
        yield
        await manager.stop()

    app = FastAPI(
        title="PaddleOCR 三模式演示",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.manager = manager

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'"
        )
        return response

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {**manager.health(), "gpu": _gpu_info()}

    @app.get("/api/samples")
    async def samples() -> dict[str, Any]:
        return {
            key: {
                "name": value["name"],
                "url": f"/api/samples/{key}",
                "mode": key,
            }
            for key, value in SAMPLES.items()
        }

    @app.get("/api/samples/{sample_id}")
    async def sample_file(sample_id: str):
        sample = SAMPLES.get(sample_id)
        if not sample:
            raise HTTPException(404, "示例不存在")
        root = config.paddleocr_dir.resolve()
        path = (root / sample["path"]).resolve()
        if root not in path.parents or not path.is_file():
            raise HTTPException(404, "本地 PaddleOCR 示例文件不存在")
        return FileResponse(path, filename=path.name)

    @app.post("/api/jobs", status_code=202)
    async def create_job(
        request: Request,
        mode: str = Form(...),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        if mode not in VALID_MODES:
            raise HTTPException(422, "mode 必须是 ocr、structure 或 vl")
        if not limiter.allow(_client_ip(request)):
            raise HTTPException(429, "提交过于频繁，请稍后重试")
        content = await file.read(config.max_upload_bytes + 1)
        filename = Path(file.filename or "upload").name
        try:
            validated = validate_upload(filename, content, mode, config)
            job = await manager.submit(
                mode=mode,
                original_name=filename,
                extension=validated.extension,
                content=content,
            )
        except UploadValidationError as exc:
            raise HTTPException(422, str(exc)) from exc
        except QueueFullError as exc:
            raise HTTPException(503, str(exc)) from exc
        return job.public_dict()

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        job = manager.get(job_id)
        if not job or job.status == "deleted":
            raise HTTPException(404, "任务不存在或已过期")
        data = job.public_dict()
        if job.result:
            result = dict(job.result)
            markdown = result.pop("markdown", "")
            result["markdown_html"] = _render_markdown(markdown, job.id)
            result["markdown_text"] = markdown
            result["artifact_urls"] = {
                name: f"/api/jobs/{job.id}/artifacts/{name}"
                for name in result.get("artifacts", [])
            }
            data["result"] = result
        return data

    @app.get("/api/jobs/{job_id}/artifacts/{name:path}")
    async def artifact(job_id: str, name: str):
        job = manager.get(job_id)
        if not job or job.status != "completed":
            raise HTTPException(404, "任务结果不存在")
        artifact_root = (config.jobs_dir / job_id / "artifacts").resolve()
        path = (artifact_root / name).resolve()
        if artifact_root not in path.parents or not path.is_file():
            raise HTTPException(404, "文件不存在")
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        disposition = "inline" if media_type.startswith("image/") else "attachment"
        return FileResponse(
            path,
            media_type=media_type,
            filename=path.name,
            content_disposition_type=disposition,
        )

    @app.delete("/api/jobs/{job_id}", status_code=204)
    async def delete_job(job_id: str):
        if not await manager.delete(job_id):
            raise HTTPException(404, "任务不存在")
        return Response(status_code=204)

    app.mount(
        "/",
        StaticFiles(directory=BASE_DIR / "static", html=True),
        name="static",
    )
    return app


app = create_app()
