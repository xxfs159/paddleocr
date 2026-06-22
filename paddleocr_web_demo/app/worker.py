from __future__ import annotations

import signal
import traceback
from multiprocessing.queues import Queue

from .inference import create_pipeline, run_inference


def worker_main(mode: str, command_queue: Queue, event_queue: Queue) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        event_queue.put({"type": "model_loading", "mode": mode})
        pipeline = create_pipeline(mode)
        event_queue.put({"type": "model_ready", "mode": mode})
    except BaseException as exc:
        event_queue.put(
            {
                "type": "worker_error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        return

    while True:
        command = command_queue.get()
        if command.get("type") == "shutdown":
            return
        if command.get("type") != "run":
            continue
        job_id = command["job_id"]

        def report(phase: str, progress: int) -> None:
            event_queue.put(
                {
                    "type": "progress",
                    "job_id": job_id,
                    "phase": phase,
                    "progress": progress,
                }
            )

        try:
            result = run_inference(
                pipeline=pipeline,
                mode=mode,
                input_path=command["input_path"],
                job_dir=command["job_dir"],
                progress=report,
            )
            event_queue.put(
                {"type": "completed", "job_id": job_id, "result": result}
            )
        except BaseException as exc:
            event_queue.put(
                {
                    "type": "failed",
                    "job_id": job_id,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
