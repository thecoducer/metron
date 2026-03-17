"""Unit tests for startup env bootstrapping."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.bootstrap import load_runtime_env


class TestLoadRuntimeEnv(unittest.TestCase):
    def test_loads_secret_files_when_env_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            flask_secret = config_dir / "flask-secret-key.txt"
            zerodha_secret = config_dir / "zerodha-token-secret.txt"
            flask_secret.write_text("flask-from-file\n", encoding="utf-8")
            zerodha_secret.write_text("zerodha-from-file\n", encoding="utf-8")

            with patch(
                "app.bootstrap._SECRET_FILE_MAP",
                {
                    "FLASK_SECRET_KEY": flask_secret,
                    "ZERODHA_TOKEN_SECRET": zerodha_secret,
                },
            ):
                with patch.dict(os.environ, {}, clear=True):
                    load_runtime_env()
                    self.assertEqual(os.environ["FLASK_SECRET_KEY"], "flask-from-file")
                    self.assertEqual(os.environ["ZERODHA_TOKEN_SECRET"], "zerodha-from-file")

    def test_env_values_take_precedence_over_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir)
            flask_secret = config_dir / "flask-secret-key.txt"
            zerodha_secret = config_dir / "zerodha-token-secret.txt"
            flask_secret.write_text("flask-from-file\n", encoding="utf-8")
            zerodha_secret.write_text("zerodha-from-file\n", encoding="utf-8")

            with patch(
                "app.bootstrap._SECRET_FILE_MAP",
                {
                    "FLASK_SECRET_KEY": flask_secret,
                    "ZERODHA_TOKEN_SECRET": zerodha_secret,
                },
            ):
                with patch.dict(
                    os.environ,
                    {
                        "FLASK_SECRET_KEY": "env-flask-secret",
                        "ZERODHA_TOKEN_SECRET": "env-zerodha-secret",
                    },
                    clear=True,
                ):
                    load_runtime_env()
                    self.assertEqual(os.environ["FLASK_SECRET_KEY"], "env-flask-secret")
                    self.assertEqual(os.environ["ZERODHA_TOKEN_SECRET"], "env-zerodha-secret")


if __name__ == "__main__":
    unittest.main()
