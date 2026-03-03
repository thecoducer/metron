"""
Unit tests for sse.py (per-user SSE client manager).
"""
import unittest
from queue import Queue

from app.sse import SSEClientManager, sse_manager


class TestSSEClientManager(unittest.TestCase):
    """Test SSEClientManager with per-user isolation."""

    def test_add_and_remove_user_client(self):
        manager = SSEClientManager()
        q = Queue()
        manager.add_client(q, google_id="user1")
        self.assertIn("user1", manager.connected_user_ids())
        manager.remove_client(q, google_id="user1")
        self.assertNotIn("user1", manager.connected_user_ids())

    def test_add_anonymous_client(self):
        manager = SSEClientManager()
        q = Queue()
        manager.add_client(q)
        # Anonymous clients are stored separately
        self.assertEqual(len(manager._anonymous_clients), 1)
        manager.remove_client(q)
        self.assertEqual(len(manager._anonymous_clients), 0)

    def test_remove_nonexistent_client(self):
        manager = SSEClientManager()
        q = Queue()
        # Should not raise
        manager.remove_client(q, google_id="nonexistent")
        manager.remove_client(q)

    def test_broadcast_to_user(self):
        """Messages sent via broadcast_to_user go only to that user."""
        manager = SSEClientManager()
        q1 = Queue()
        q2 = Queue()
        manager.add_client(q1, google_id="user1")
        manager.add_client(q2, google_id="user2")

        manager.broadcast_to_user("user1", "hello_user1")

        self.assertEqual(q1.get_nowait(), "hello_user1")
        self.assertTrue(q2.empty())

    def test_broadcast_all(self):
        """broadcast_all sends to all user + anonymous clients."""
        manager = SSEClientManager()
        q1 = Queue()
        q2 = Queue()
        q_anon = Queue()
        manager.add_client(q1, google_id="user1")
        manager.add_client(q2, google_id="user2")
        manager.add_client(q_anon)

        manager.broadcast_all("global_msg")

        self.assertEqual(q1.get_nowait(), "global_msg")
        self.assertEqual(q2.get_nowait(), "global_msg")
        self.assertEqual(q_anon.get_nowait(), "global_msg")

    def test_connected_user_ids(self):
        manager = SSEClientManager()
        q1 = Queue()
        q2 = Queue()
        manager.add_client(q1, google_id="user1")
        manager.add_client(q2, google_id="user2")

        ids = manager.connected_user_ids()
        self.assertEqual(ids, {"user1", "user2"})

    def test_connected_user_ids_empty(self):
        manager = SSEClientManager()
        self.assertEqual(manager.connected_user_ids(), set())

    def test_multiple_clients_per_user(self):
        """One user can have multiple browser tabs / connections."""
        manager = SSEClientManager()
        q1 = Queue()
        q2 = Queue()
        manager.add_client(q1, google_id="user1")
        manager.add_client(q2, google_id="user1")

        manager.broadcast_to_user("user1", "msg")

        self.assertEqual(q1.get_nowait(), "msg")
        self.assertEqual(q2.get_nowait(), "msg")

    def test_remove_one_of_multiple_clients(self):
        manager = SSEClientManager()
        q1 = Queue()
        q2 = Queue()
        manager.add_client(q1, google_id="user1")
        manager.add_client(q2, google_id="user1")

        manager.remove_client(q1, google_id="user1")

        # user1 should still be connected (q2 remains)
        self.assertIn("user1", manager.connected_user_ids())

        manager.remove_client(q2, google_id="user1")
        # Now fully disconnected
        self.assertNotIn("user1", manager.connected_user_ids())

    def test_user_isolation_no_cross_delivery(self):
        """Ensure user1 messages never reach user2."""
        manager = SSEClientManager()
        q1 = Queue()
        q2 = Queue()
        manager.add_client(q1, google_id="user1")
        manager.add_client(q2, google_id="user2")

        manager.broadcast_to_user("user1", "secret")

        self.assertEqual(q1.get_nowait(), "secret")
        self.assertTrue(q2.empty())

    def test_global_instance_exists(self):
        self.assertIsInstance(sse_manager, SSEClientManager)


if __name__ == '__main__':
    unittest.main()
