"""Per-user SSE client management and targeted broadcasting."""

import threading
from queue import Queue
from typing import Dict, List, Optional, Set

from .logging_config import logger


class SSEClientManager:
    """Manages per-user SSE client queues. Thread-safe."""

    def __init__(self):
        self._user_clients: Dict[str, List[Queue]] = {}
        self._anonymous_clients: List[Queue] = []
        self.lock = threading.Lock()

    def add_client(self, client_queue: Queue, google_id: Optional[str] = None) -> None:
        with self.lock:
            if google_id:
                self._user_clients.setdefault(google_id, []).append(client_queue)
            else:
                self._anonymous_clients.append(client_queue)

    def remove_client(self, client_queue: Queue, google_id: Optional[str] = None) -> None:
        with self.lock:
            if google_id and google_id in self._user_clients:
                try:
                    self._user_clients[google_id].remove(client_queue)
                except ValueError:
                    pass
                if not self._user_clients[google_id]:
                    del self._user_clients[google_id]
            else:
                try:
                    self._anonymous_clients.remove(client_queue)
                except ValueError:
                    pass

    def _send_to_queues(self, queues: List[Queue], message: str, google_id: Optional[str] = None) -> List[tuple]:
        """Send message to queues, return list of (queue, google_id) for failures."""
        failed = []
        for q in queues[:]:
            try:
                q.put_nowait(message)
            except Exception:
                logger.exception("Failed to send SSE message")
                failed.append((q, google_id))
        return failed

    def broadcast_to_user(self, google_id: str, message: str) -> None:
        with self.lock:
            queues = self._user_clients.get(google_id, [])
            failed = self._send_to_queues(queues, message, google_id)
        for q, gid in failed:
            self.remove_client(q, gid)

    def broadcast_all(self, message: str) -> None:
        failed = []
        with self.lock:
            for gid, queues in self._user_clients.items():
                failed.extend(self._send_to_queues(queues, message, gid))
            failed.extend(self._send_to_queues(self._anonymous_clients, message, None))
        for q, gid in failed:
            self.remove_client(q, gid)

    def connected_user_ids(self) -> Set[str]:
        with self.lock:
            return set(self._user_clients.keys())


sse_manager = SSEClientManager()
