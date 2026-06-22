from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import time
from typing import Any


VALID_MODES = {"ocr", "structure", "vl"}
TERMINAL_STATES = {"completed", "failed", "deleted"}


@dataclass
class Job:
    id: str
    mode: str
    original_name: str
    input_path: str
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    status: str = "queued"
    phase: str = "等待处理"
    progress: int = 0
    queue_position: int | None = None
    error: str | None = None
    result: dict[str, Any] | None = None

    def update(self, **changes: Any) -> None:
        for key, value in changes.items():
            setattr(self, key, value)
        self.updated_at = time()

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("input_path", None)
        return data

