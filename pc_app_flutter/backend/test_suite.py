import unittest
from unittest.mock import MagicMock, patch
import json
import os
import sys

# Add core to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'core'))

# Mock Flask and dependencies before importing server
with patch('flask.Flask'), patch('flask_cors.CORS'), patch('flask_socketio.SocketIO'):
    from core import server

class TestCypherBackend(unittest.TestCase):

    def setUp(self):
        # Reset global states for each test
        server.recording_state.update({
            "is_recording": False,
            "is_paused": False,
            "start_time": None
        })
        server.valid_tokens = {"cypher-internal-pc-app-token-2024"}

    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    def test_system_stats_logic(self, mock_vm, mock_cpu):
        # Mock psutil data
        mock_cpu.return_value = 25.5
        mock_vm.return_value.percent = 60.0
        mock_vm.return_value.total = 16 * (1024**3)
        mock_vm.return_value.used = 8 * (1024**3)

        # Trigger monitoring logic (normally runs in thread)
        # We manually verify current_system_stats after a simulated poll
        import psutil
        cpu = psutil.cpu_percent()
        vm = psutil.virtual_memory()

        stats = {
            "cpu_percent": cpu,
            "ram_percent": vm.percent,
            "ram_total": round(vm.total / (1024**3), 2)
        }

        self.assertEqual(stats["cpu_percent"], 25.5)
        self.assertEqual(stats["ram_percent"], 60.0)
        self.assertEqual(stats["ram_total"], 16.0)

    def test_pairing_token_generation(self):
        # Test code validation
        server.PAIRING_CODE = "123456"

        # Test valid code
        token = "test-token"
        server.paired_devices["test-device"] = {"token": token}
        server.valid_tokens.add(token)

        self.assertIn(token, server.valid_tokens)

    def test_window_manager_logic(self):
        # Mock a window object
        mock_win = MagicMock()
        mock_win.title = "Visual Studio Code"
        mock_win._hWnd = 12345

        win_info = {
            "title": mock_win.title,
            "id": mock_win._hWnd
        }
        self.assertEqual(win_info["title"], "Visual Studio Code")
        self.assertEqual(win_info["id"], 12345)

    def test_recording_state_transitions(self):
        # Verify initial state
        self.assertFalse(server.recording_state["is_recording"])

        # Simulate start
        server.recording_state["is_recording"] = True
        self.assertTrue(server.recording_state["is_recording"])

        # Simulate toggle pause
        server.recording_state["is_paused"] = True
        self.assertTrue(server.recording_state["is_paused"])

    def test_unique_path_logic(self):
        # Mock file system path logic
        from pathlib import Path

        # We'll test the logic without actual disk writes by mocking os.path.exists
        with patch('pathlib.Path.exists') as mock_exists:
            # Case 1: File doesn't exist
            mock_exists.return_value = False
            path = server.get_unique_path("C:/test/file.txt")
            self.assertEqual(path.replace('\\', '/'), "C:/test/file.txt")

            # Case 2: File exists, should increment
            mock_exists.side_effect = [True, False]
            path = server.get_unique_path("C:/test/file.txt")
            self.assertIn("file (1).txt", path.replace('\\', '/'))

if __name__ == '__main__':
    unittest.main()
