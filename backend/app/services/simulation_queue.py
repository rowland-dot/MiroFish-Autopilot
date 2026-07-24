"""Simulation queue: slot (running) + queue (waiting) capacity guard.

Free-tier RAM fits one heavy OASIS run; a second concurrent run gets
OOM-killed. This limits concurrency: SLOT_LIMIT run at once, QUEUE_LIMIT
wait. In-memory only (single Flask process, ephemeral disk) — queued
jobs are lost on restart, which is accepted.

Pure decision + FIFO list. Thread-safe (mutated from the monitor daemon
thread and from request threads).
"""

import threading


class QueueFull(Exception):
    """Raised when enqueue is attempted past QUEUE_LIMIT."""


class SimulationQueue:
    def __init__(self, slot_limit: int = 1, queue_limit: int = 2):
        self.slot_limit = slot_limit
        self.queue_limit = queue_limit
        self._queue: list = []          # FIFO of start-request payloads
        self._lock = threading.RLock()

    def decide(self, running_count: int) -> str:
        """'start' if a slot is free, else 'queue' if room, else 'full'."""
        with self._lock:
            if running_count < self.slot_limit:
                return "start"
            if len(self._queue) < self.queue_limit:
                return "queue"
            return "full"

    def enqueue(self, entry: dict) -> None:
        with self._lock:
            if len(self._queue) >= self.queue_limit:
                raise QueueFull(f"queue at limit {self.queue_limit}")
            self._queue.append(entry)

    def dequeue(self):
        """Pop and return the oldest entry, or None if empty."""
        with self._lock:
            if not self._queue:
                return None
            return self._queue.pop(0)

    def peek(self):
        """Return the oldest entry without removing it, or None if empty.

        Used by promote_next to read the next job's graph_id before acquiring
        the per-graph lock (preserves graph->submit lock ordering)."""
        with self._lock:
            return self._queue[0] if self._queue else None

    def cancel(self, simulation_id: str) -> bool:
        """Remove a queued id (user pressed 取消排队). True if removed."""
        return self.remove(simulation_id)

    def remove(self, simulation_id: str) -> bool:
        """Evict a queued id (also used by delete, B7). True if removed."""
        with self._lock:
            for i, e in enumerate(self._queue):
                if e.get("simulation_id") == simulation_id:
                    self._queue.pop(i)
                    return True
            return False

    def contains(self, simulation_id: str) -> bool:
        with self._lock:
            return any(e.get("simulation_id") == simulation_id for e in self._queue)

    def get(self, simulation_id: str):
        with self._lock:
            for e in self._queue:
                if e.get("simulation_id") == simulation_id:
                    return e
            return None

    def ids(self) -> list:
        with self._lock:
            return [e.get("simulation_id") for e in self._queue]

    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    def capacity_full(self, running_count: int) -> bool:
        """True when no slot free AND queue full — start section disabled."""
        with self._lock:
            return running_count >= self.slot_limit and len(self._queue) >= self.queue_limit
