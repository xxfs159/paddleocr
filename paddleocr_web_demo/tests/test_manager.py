from __future__ import annotations

import time

import pytest

from paddleocr.paddleocr_web_demo.app.config import Settings
from paddleocr.paddleocr_web_demo.app.manager import JobManager, QueueFullError


@pytest.mark.asyncio
async def test_queue_limit_and_delete(tmp_path):
    manager = JobManager(Settings(data_dir=tmp_path, max_waiting_jobs=1))
    first = await manager.submit("ocr", "one.png", ".png", b"one")
    with pytest.raises(QueueFullError):
        await manager.submit("ocr", "two.png", ".png", b"two")
    assert await manager.delete(first.id)
    second = await manager.submit("ocr", "two.png", ".png", b"two")
    assert second.queue_position == 1


def test_orphan_cleanup(tmp_path):
    config = Settings(data_dir=tmp_path, result_ttl_seconds=1)
    manager = JobManager(config)
    old = config.jobs_dir / "old"
    old.mkdir(parents=True)
    past = time.time() - 10
    old.touch()
    import os

    os.utime(old, (past, past))
    manager._remove_orphaned_directories()
    assert not old.exists()

