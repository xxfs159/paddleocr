from __future__ import annotations

import asyncio
import multiprocessing as mp
import queue
import shutil
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from .config import Settings
from .schemas import Job, TERMINAL_STATES
from .worker import worker_main


class QueueFullError(RuntimeError):
    pass


class JobManager:
    def __init__(self, config: Settings) -> None:
        self.config = config
        self.jobs: dict[str, Job] = {}
        self.pending: deque[str] = deque()
        self.active_job_id: str | None = None
        self.current_model: str | None = None
        self.model_state = "idle"
        self._lock = asyncio.Lock()
        self._runner_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._running = False
        self._ctx = mp.get_context("spawn")
        self._worker: mp.Process | None = None
        self._command_queue: Any = None
        self._event_queue: Any = None

    async def start(self) -> None:
        self.config.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._remove_orphaned_directories()
        self._running = True
        self._runner_task = asyncio.create_task(self._run_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        self._running = False
        tasks = [task for task in (self._runner_task, self._cleanup_task) if task]
        for task in tasks:
            if task:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._stop_worker()

    async def submit(
        self,
        mode: str,
        original_name: str,
        extension: str,
        content: bytes,
    ) -> Job:
        async with self._lock:
            if len(self.pending) >= self.config.max_waiting_jobs:
                raise QueueFullError("等待队列已满，请稍后重试")
            job_id = uuid.uuid4().hex
            job_dir = self.config.jobs_dir / job_id
            job_dir.mkdir(parents=True)
            input_path = job_dir / f"input{extension}"
            input_path.write_bytes(content)
            job = Job(
                id=job_id,
                mode=mode,
                original_name=original_name,
                input_path=str(input_path),
            )
            self.jobs[job_id] = job
            self.pending.append(job_id)
            self._refresh_queue_positions()
            return job

    async def delete(self, job_id: str) -> bool:
        async with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
            job.update(status="deleted", phase="已删除", progress=0)
            self.pending = deque(item for item in self.pending if item != job_id)
            is_active = self.active_job_id == job_id
            self._refresh_queue_positions()
        if is_active:
            await self._stop_worker()
        shutil.rmtree(self.config.jobs_dir / job_id, ignore_errors=True)
        return True

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "current_model": self.current_model,
            "model_state": self.model_state,
            "active_job_id": self.active_job_id,
            "waiting_jobs": len(self.pending),
        }

    async def _run_loop(self) -> None:
        while self._running:
            job: Job | None = None
            async with self._lock:
                while self.pending:
                    job_id = self.pending.popleft()
                    candidate = self.jobs.get(job_id)
                    if candidate and candidate.status == "queued":
                        job = candidate
                        self.active_job_id = candidate.id
                        candidate.queue_position = None
                        self._refresh_queue_positions()
                        break
            if not job:
                await asyncio.sleep(0.2)
                continue
            try:
                await self._process(job)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if job.status != "deleted":
                    job.update(
                        status="failed",
                        phase="处理失败",
                        progress=100,
                        error=str(exc),
                    )
            finally:
                async with self._lock:
                    if self.active_job_id == job.id:
                        self.active_job_id = None

    async def _process(self, job: Job) -> None:
        await self._ensure_worker(job.mode, job)
        if job.status == "deleted":
            return
        job.update(status="running", phase="提交到 GPU", progress=25)
        self._command_queue.put(
            {
                "type": "run",
                "job_id": job.id,
                "input_path": job.input_path,
                "job_dir": str(self.config.jobs_dir / job.id),
            }
        )
        deadline = time.monotonic() + self.config.job_timeout
        while time.monotonic() < deadline:
            if job.status == "deleted":
                return
            event = await self._next_event()
            if event is None:
                continue
            if event.get("job_id") != job.id:
                continue
            event_type = event.get("type")
            if event_type == "progress":
                job.update(
                    status="running",
                    phase=event["phase"],
                    progress=event["progress"],
                )
            elif event_type == "completed":
                job.update(
                    status="completed",
                    phase="处理完成",
                    progress=100,
                    result=event["result"],
                )
                return
            elif event_type == "failed":
                self._write_error_log(job, event)
                await self._stop_worker()
                raise RuntimeError(event.get("error", "推理失败"))
        await self._stop_worker()
        raise TimeoutError("任务处理超时")

    async def _ensure_worker(self, mode: str, job: Job) -> None:
        if self._worker and self._worker.is_alive() and self.current_model == mode:
            return
        await self._stop_worker()
        job.update(status="loading_model", phase="正在加载模型", progress=10)
        self.model_state = "loading"
        self.current_model = mode
        self._command_queue = self._ctx.Queue()
        self._event_queue = self._ctx.Queue()
        self._worker = self._ctx.Process(
            target=worker_main,
            args=(mode, self._command_queue, self._event_queue),
            daemon=False,
            name=f"paddleocr-{mode}-worker",
        )
        self._worker.start()
        deadline = time.monotonic() + self.config.worker_start_timeout
        while time.monotonic() < deadline:
            if job.status == "deleted":
                return
            event = await self._next_event()
            if event is None:
                continue
            if event.get("type") == "model_ready":
                self.model_state = "ready"
                job.update(phase="模型加载完成", progress=20)
                return
            if event.get("type") == "worker_error":
                self._write_error_log(job, event)
                await self._stop_worker()
                raise RuntimeError(event.get("error", "模型加载失败"))
        await self._stop_worker()
        raise TimeoutError("模型加载超时")

    async def _next_event(self) -> dict[str, Any] | None:
        if not self._event_queue:
            await asyncio.sleep(0.2)
            return None
        try:
            return self._event_queue.get_nowait()
        except queue.Empty:
            if self._worker and not self._worker.is_alive():
                raise RuntimeError("推理进程意外退出")
            await asyncio.sleep(0.2)
            return None

    async def _stop_worker(self) -> None:
        worker = self._worker
        if worker:
            if worker.is_alive():
                try:
                    if self._command_queue:
                        self._command_queue.put({"type": "shutdown"})
                    await asyncio.to_thread(worker.join, 5)
                except Exception:
                    pass
            if worker.is_alive():
                worker.terminate()
                await asyncio.to_thread(worker.join, 5)
            if worker.is_alive():
                worker.kill()
                await asyncio.to_thread(worker.join, 2)
        for q in (self._command_queue, self._event_queue):
            if q:
                try:
                    q.close()
                except Exception:
                    pass
        self._worker = None
        self._command_queue = None
        self._event_queue = None
        self.current_model = None
        self.model_state = "idle"

    async def _cleanup_loop(self) -> None:
        while self._running:
            await asyncio.sleep(60)
            cutoff = time.time() - self.config.result_ttl_seconds
            expired = [
                job_id
                for job_id, job in self.jobs.items()
                if job.status in TERMINAL_STATES and job.updated_at < cutoff
            ]
            for job_id in expired:
                shutil.rmtree(self.config.jobs_dir / job_id, ignore_errors=True)
                self.jobs.pop(job_id, None)

    def _refresh_queue_positions(self) -> None:
        for position, job_id in enumerate(self.pending, start=1):
            job = self.jobs.get(job_id)
            if job:
                job.queue_position = position

    def _write_error_log(self, job: Job, event: dict[str, Any]) -> None:
        path = self.config.jobs_dir / job.id / "error.log"
        try:
            path.write_text(
                event.get("traceback") or event.get("error") or "Unknown worker error",
                encoding="utf-8",
            )
        except OSError:
            pass

    def _remove_orphaned_directories(self) -> None:
        cutoff = time.time() - self.config.result_ttl_seconds
        for path in self.config.jobs_dir.iterdir():
            try:
                if path.is_dir() and path.stat().st_mtime < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
            except FileNotFoundError:
                pass


class FakeJobManager:
    """Small in-memory manager used by API tests."""

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def submit(
        self, mode: str, original_name: str, extension: str, content: bytes
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            mode=mode,
            original_name=original_name,
            input_path="/tmp/fake",
        )
        self.jobs[job.id] = job
        return job

    async def delete(self, job_id: str) -> bool:
        return self.jobs.pop(job_id, None) is not None

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "current_model": None,
            "model_state": "idle",
            "active_job_id": None,
            "waiting_jobs": 0,
        }
