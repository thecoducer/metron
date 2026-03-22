"""
Unit tests for api/google_auth.py — OAuth flow helpers.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.api.google_auth import (
    USER_SCOPES,
    _get_client_config,
    build_oauth_flow,
    credentials_from_dict,
    credentials_to_dict,
    exchange_code_for_credentials,
    get_user_info,
)


class TestGetClientConfig(unittest.TestCase):
    @patch.dict(os.environ, {"GOOGLE_OAUTH_CREDENTIALS": '{"web": {"client_id": "id1"}}'})
    def test_from_env_var(self):
        result = _get_client_config()
        self.assertEqual(result, {"web": {"client_id": "id1"}})

    @patch.dict(os.environ, {"GOOGLE_OAUTH_CREDENTIALS": "bad-json"})
    def test_from_env_var_invalid_json(self):
        with self.assertRaises(ValueError):
            _get_client_config()

    @patch.dict(os.environ, {}, clear=True)
    def test_from_local_file(self):
        config_data = {"web": {"client_id": "local_id"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            with patch("app.api.google_auth._LOCAL_CLIENT_SECRETS", f.name):
                result = _get_client_config()
                self.assertEqual(result, config_data)
            os.unlink(f.name)

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists", return_value=False)
    def test_no_config_raises(self, mock_exists):
        with self.assertRaises(FileNotFoundError):
            _get_client_config()


class TestBuildOAuthFlow(unittest.TestCase):
    @patch("app.api.google_auth._get_client_config")
    @patch("app.api.google_auth.Flow.from_client_config")
    def test_build_flow(self, mock_from_config, mock_get_config):
        mock_get_config.return_value = {"web": {"client_id": "id"}}
        mock_flow = Mock()
        mock_from_config.return_value = mock_flow

        result = build_oauth_flow("http://localhost/callback")

        mock_from_config.assert_called_once_with(
            {"web": {"client_id": "id"}},
            scopes=USER_SCOPES,
            redirect_uri="http://localhost/callback",
        )
        self.assertEqual(result, mock_flow)


class TestExchangeCodeForCredentials(unittest.TestCase):
    @patch("app.api.google_auth.build_oauth_flow")
    def test_exchange(self, mock_build):
        mock_flow = Mock()
        mock_flow.credentials = Mock()
        mock_build.return_value = mock_flow

        result = exchange_code_for_credentials("auth_code", "http://localhost/cb")

        mock_flow.fetch_token.assert_called_once_with(code="auth_code")
        self.assertIs(result, mock_flow.credentials)


class TestCredentialsFromDict(unittest.TestCase):
    def test_basic(self):
        data = {
            "token": "access_tok",
            "refresh_token": "refresh_tok",
            "token_uri": "https://accounts.google.com/o/oauth2/token",
            "client_id": "cid",
            "client_secret": "csecret",
            "scopes": ["openid"],
        }
        creds = credentials_from_dict(data)
        self.assertEqual(creds.token, "access_tok")
        self.assertEqual(creds.refresh_token, "refresh_tok")
        self.assertEqual(creds.client_id, "cid")

    def test_defaults(self):
        data = {"token": "t"}
        creds = credentials_from_dict(data)
        self.assertEqual(creds.token_uri, "https://oauth2.googleapis.com/token")
        # pyrefly: ignore [no-matching-overload]
        self.assertEqual(list(creds.scopes), USER_SCOPES)


class TestCredentialsToDict(unittest.TestCase):
    def test_serialization(self):
        creds = Mock()
        creds.token = "tok"
        creds.refresh_token = "rtok"
        creds.token_uri = "https://example.com/token"
        creds.client_id = "cid"
        creds.client_secret = "cs"
        creds.scopes = ["openid", "email"]

        result = credentials_to_dict(creds)
        self.assertEqual(result["token"], "tok")
        self.assertEqual(result["refresh_token"], "rtok")
        self.assertEqual(result["scopes"], ["openid", "email"])

    def test_none_scopes_defaults(self):
        creds = Mock()
        creds.token = "tok"
        creds.refresh_token = "rtok"
        creds.token_uri = "uri"
        creds.client_id = "cid"
        creds.client_secret = "cs"
        creds.scopes = None

        result = credentials_to_dict(creds)
        self.assertEqual(result["scopes"], USER_SCOPES)


class TestGetUserInfo(unittest.TestCase):
    @patch("googleapiclient.discovery.build")
    def test_fetches_user_info(self, mock_build):
        mock_service = Mock()
        mock_build.return_value = mock_service
        mock_service.userinfo.return_value.get.return_value.execute.return_value = {
            "id": "123",
            "email": "test@test.com",
            "name": "Test",
            "picture": "pic.jpg",
        }

        creds = Mock()
        result = get_user_info(creds)

        mock_build.assert_called_once_with("oauth2", "v2", credentials=creds, static_discovery=True)
        self.assertEqual(result["id"], "123")
        self.assertEqual(result["email"], "test@test.com")


if __name__ == "__main__":
    unittest.main()
