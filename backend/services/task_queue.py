"""
In-process async task queue for long-running operations.

Moves heavy work (imports, correlation) off the HTTP request path so that
API responses return immediately with a task ID.  Callers poll
``/api/tasks/{task_id}`` for progress and results.

Design:
  - Single asyncio worker per task type (import / correlation) to serialise
    writes and avoid SQLite lock contention between concurrent tasks.
  - Task state is kept in-memory (dict).  If the process restarts, pending
    tasks are lost — acceptable for this workload since the raw data is
    persisted and can be re-imported.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class TaskInfo:
    id: str
    task_type: str  # "import", "correlation", "cleanup"
    status: TaskStatus = TaskStatus.PENDING
    progress: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "status": self.status.value,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class TaskQueue:
    """Simple asyncio-based task queue with per-type serialization."""

    def __init__(self, max_history: int = 200):
        self._tasks: Dict[str, TaskInfo] = {}
        self._queues: Dict[str, asyncio.Queue] = {}
        self._workers: Dict[str, asyncio.Task] = {}
        self._max_history = max_history

    def _ensure_worker(self, task_type: str) -> None:
        """Start a worker for *task_type* if one isn't already running."""
        if task_type in self._workers and not self._workers[task_type].done():
            return
        if task_type not in self._queues:
            self._queues[task_type] = asyncio.Queue()
        self._workers[task_type] = asyncio.create_task(
            self._worker_loop(task_type),
            name=f"task-worker-{task_type}",
        )

    async def _worker_loop(self, task_type: str) -> None:
        """Process tasks of *task_type* one at a time."""
        queue = self._queues[task_type]
        while True:
            task_id, coro_factory = await queue.get()
            task_info = self._tasks.get(task_id)
            if task_info is None:
                queue.task_done()
                continue

            task_info.status = TaskStatus.RUNNING
            task_info.started_at = datetime.utcnow()
            logger.info(f"Task {task_id} ({task_type}) started")

            try:
                result = await coro_factory()
                task_info.status = TaskStatus.SUCCESS
                task_info.result = result
                logger.info(f"Task {task_id} ({task_type}) completed successfully")
            except Exception as exc:
                task_info.status = TaskStatus.FAILED
                task_info.error = str(exc)
                logger.exception(f"Task {task_id} ({task_type}) failed: {exc}")
            finally:
                task_info.completed_at = datetime.utcnow()
                queue.task_done()
                self._prune_history()

    def submit(
        self,
        task_type: str,
        coro_factory: Callable[[], Coroutine],
    ) -> str:
        """
        Enqueue a task and return its ID immediately.

        *coro_factory* is a zero-arg callable that returns an awaitable.
        It is NOT called until the worker picks up the task — this avoids
        creating the coroutine before it can be awaited.
        """
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = TaskInfo(id=task_id, task_type=task_type)
        self._ensure_worker(task_type)
        self._queues[task_type].put_nowait((task_id, coro_factory))
        logger.info(f"Task {task_id} ({task_type}) enqueued")
        return task_id

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        task_type: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> list[TaskInfo]:
        tasks = list(self._tasks.values())
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]

    def _prune_history(self) -> None:
        """Remove oldest completed tasks when history exceeds the limit."""
        if len(self._tasks) <= self._max_history:
            return
        completed = sorted(
            (t for t in self._tasks.values() if t.status in (TaskStatus.SUCCESS, TaskStatus.FAILED)),
            key=lambda t: t.completed_at or t.created_at,
        )
        while len(self._tasks) > self._max_history and completed:
            old = completed.pop(0)
            self._tasks.pop(old.id, None)

    async def shutdown(self) -> None:
        """Cancel all workers (called on app shutdown)."""
        for worker in self._workers.values():
            worker.cancel()
        for worker in self._workers.values():
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._workers.clear()
        logger.info("Task queue shut down")


# ── Module-level singleton ────────────────────────────────────────────
task_queue = TaskQueue()
