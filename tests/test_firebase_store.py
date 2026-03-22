"""
Unit tests for firebase_store.py — Firestore user CRUD, credentials, sessions, and PIN.
"""

import os
import unittest
from unittest.mock import Mock, patch

import app.firebase_store as fs


# Helper: create a mock Firestore document
def _mock_doc(exists=True, data=None):
    doc = Mock()
    doc.exists = exists
    doc.to_dict.return_value = data if data else {}
    return doc


def _mock_ref(doc):
    ref = Mock()
    ref.get.return_value = doc
    return ref


class TestResolveFirebaseCredential(unittest.TestCase):
    """Test _resolve_firebase_credential resolution order."""

    @patch.dict(os.environ, {"FIREBASE_CREDENTIALS": '{"type": "service_account"}'})
    @patch("app.firebase_store.logger")
    def test_env_var_json_string(self, mock_logger):
        with patch("firebase_admin.credentials") as mock_creds:
            mock_creds.Certificate.return_value = "cert_obj"
            result = fs._resolve_firebase_credential()
            mock_creds.Certificate.assert_called_once_with({"type": "service_account"})
            self.assertEqual(result, "cert_obj")

    @patch.dict(os.environ, {"FIREBASE_CREDENTIALS": "not-json"}, clear=False)
    @patch("app.firebase_store.logger")
    def test_env_var_invalid_json_falls_through(self, mock_logger):
        with (
            patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": ""}, clear=False),
            patch("os.path.exists", return_value=False),
            patch("firebase_admin.credentials") as mock_creds,
        ):
            mock_creds.ApplicationDefault.return_value = "adc_obj"
            result = fs._resolve_firebase_credential()
            self.assertEqual(result, "adc_obj")

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists")
    @patch("app.firebase_store.logger")
    def test_google_application_credentials_file(self, mock_logger, mock_exists):
        # First call for GOOGLE_APPLICATION_CREDENTIALS check, second for local path
        mock_exists.side_effect = lambda p: p == "/path/cred.json"
        with (
            patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "/path/cred.json"}),
            patch("firebase_admin.credentials") as mock_creds,
        ):
            mock_creds.Certificate.return_value = "cert_from_file"
            result = fs._resolve_firebase_credential()
            mock_creds.Certificate.assert_called_with("/path/cred.json")
            self.assertEqual(result, "cert_from_file")

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists")
    @patch("app.firebase_store.logger")
    def test_local_file_fallback(self, mock_logger, mock_exists):
        mock_exists.side_effect = lambda p: p == fs._LOCAL_CREDENTIALS_PATH
        with patch("firebase_admin.credentials") as mock_creds:
            mock_creds.Certificate.return_value = "local_cert"
            fs._resolve_firebase_credential()
            mock_creds.Certificate.assert_called_with(fs._LOCAL_CREDENTIALS_PATH)

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists", return_value=False)
    @patch("app.firebase_store.logger")
    def test_adc_fallback(self, mock_logger, mock_exists):
        with patch("firebase_admin.credentials") as mock_creds:
            mock_creds.ApplicationDefault.return_value = "adc"
            result = fs._resolve_firebase_credential()
            mock_creds.ApplicationDefault.assert_called_once()
            self.assertEqual(result, "adc")


class TestDb(unittest.TestCase):
    """Test _db() lazy initialization."""

    def setUp(self):
        # Reset global client before each test
        fs._firestore_client = None

    def tearDown(self):
        fs._firestore_client = None

    @patch("app.firebase_store._resolve_firebase_credential")
    @patch("app.firebase_store.logger")
    def test_lazy_init(self, mock_logger, mock_resolve):
        mock_resolve.return_value = Mock()
        mock_app = Mock()
        mock_app.project_id = "test-project"
        mock_cred = Mock()
        mock_cred.get_credential.return_value = "cred_inst"
        mock_app.credential = mock_cred

        with (
            patch("firebase_admin._apps", {}),
            patch("firebase_admin.initialize_app") as mock_init,
            patch("firebase_admin.get_app", return_value=mock_app),
            patch("google.cloud.firestore.Client") as mock_client,
        ):
            mock_client.return_value = "firestore_client"
            result = fs._db()
            self.assertEqual(result, "firestore_client")
            mock_init.assert_called_once()

    def test_returns_cached_client(self):
        # pyrefly: ignore [bad-assignment]
        fs._firestore_client = "cached"
        result = fs._db()
        self.assertEqual(result, "cached")


class TestUserCRUD(unittest.TestCase):
    """Test user CRUD operations."""

    @patch("app.firebase_store._user_ref")
    def test_get_user_exists(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={"email": "a@b.com", "google_id": "g1"})
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_user("g1")
        # pyrefly: ignore [unsupported-operation]
        self.assertEqual(result["email"], "a@b.com")

    @patch("app.firebase_store._user_ref")
    def test_get_user_not_found(self, mock_ref_fn):
        doc = _mock_doc(exists=False)
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_user("g_missing")
        self.assertIsNone(result)

    @patch("app.firebase_store._user_ref")
    def test_get_user_firestore_error(self, mock_ref_fn):
        from google.api_core import exceptions as gcp_exceptions

        ref = Mock()
        ref.get.side_effect = gcp_exceptions.GoogleAPICallError("fail")
        mock_ref_fn.return_value = ref
        with self.assertRaises(gcp_exceptions.GoogleAPICallError):
            fs.get_user("g1")

    @patch("app.firebase_store.encrypt_google_credentials", return_value="encrypted")
    @patch("app.firebase_store._user_ref")
    def test_upsert_user_create(self, mock_ref_fn, mock_enc):
        doc = _mock_doc(exists=False)
        updated_doc = _mock_doc(exists=True, data={"google_id": "g1", "email": "a@b.com"})
        ref = Mock()
        ref.get.side_effect = [doc, updated_doc]
        mock_ref_fn.return_value = ref

        result = fs.upsert_user("g1", "a@b.com", "Name", "pic.jpg", {"token": "t"})
        ref.set.assert_called_once()
        self.assertEqual(result["email"], "a@b.com")

    @patch("app.firebase_store.encrypt_google_credentials", return_value="encrypted")
    @patch("app.firebase_store._user_ref")
    def test_upsert_user_update(self, mock_ref_fn, mock_enc):
        doc = _mock_doc(exists=True, data={"google_id": "g1", "email": "old@b.com"})
        updated_doc = _mock_doc(exists=True, data={"google_id": "g1", "email": "a@b.com"})
        ref = Mock()
        ref.get.side_effect = [doc, updated_doc]
        mock_ref_fn.return_value = ref

        result = fs.upsert_user("g1", "a@b.com", "Name", "pic.jpg", {"token": "t"}, spreadsheet_id="sid")
        ref.update.assert_called_once()
        self.assertEqual(result["email"], "a@b.com")

    @patch("app.firebase_store._user_ref")
    def test_update_spreadsheet_id(self, mock_ref_fn):
        ref = Mock()
        mock_ref_fn.return_value = ref
        fs.update_spreadsheet_id("g1", "sheet_123")
        ref.update.assert_called_once_with({"spreadsheet_id": "sheet_123"})


class TestGoogleCredentials(unittest.TestCase):
    @patch("app.firebase_store.decrypt_google_credentials", return_value={"token": "t"})
    @patch("app.firebase_store._user_ref")
    def test_get_google_credentials_success(self, mock_ref_fn, mock_dec):
        doc = _mock_doc(exists=True, data={"google_credentials": "enc_data"})
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_google_credentials("g1")
        self.assertEqual(result, {"token": "t"})

    @patch("app.firebase_store._user_ref")
    def test_get_google_credentials_no_data(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={})
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_google_credentials("g1")
        self.assertIsNone(result)

    @patch("app.firebase_store._user_ref")
    def test_get_google_credentials_not_exists(self, mock_ref_fn):
        doc = _mock_doc(exists=False)
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_google_credentials("g1")
        self.assertIsNone(result)

    @patch("app.firebase_store.decrypt_google_credentials", side_effect=Exception("decrypt fail"))
    @patch("app.firebase_store._user_ref")
    def test_get_google_credentials_decrypt_fail(self, mock_ref_fn, mock_dec):
        doc = _mock_doc(exists=True, data={"google_credentials": "enc_data"})
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_google_credentials("g1")
        self.assertIsNone(result)

    @patch("app.firebase_store.encrypt_google_credentials", return_value="enc")
    @patch("app.firebase_store._user_ref")
    def test_update_google_credentials(self, mock_ref_fn, mock_enc):
        ref = Mock()
        mock_ref_fn.return_value = ref
        fs.update_google_credentials("g1", {"token": "new"})
        ref.update.assert_called_once_with({"google_credentials": "enc"})


class TestZerodhaAccounts(unittest.TestCase):
    @patch("app.firebase_store.encrypt_credential", side_effect=lambda v, p: f"enc_{v}")
    @patch("app.firebase_store._user_ref")
    def test_add_zerodha_account(self, mock_ref_fn, mock_enc):
        doc = _mock_doc(exists=True, data={"zerodha_accounts": []})
        ref = Mock()
        ref.get.return_value = doc
        mock_ref_fn.return_value = ref
        fs.add_zerodha_account("g1", "MyAcc", "key1", "secret1", pin="pin123")
        ref.update.assert_called_once()
        accounts = ref.update.call_args[0][0]["zerodha_accounts"]
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["account_name"], "MyAcc")

    @patch("app.firebase_store._user_ref")
    def test_add_zerodha_account_no_pin_raises(self, mock_ref_fn):
        with self.assertRaises(ValueError):
            fs.add_zerodha_account("g1", "Acc", "k", "s", pin="")

    @patch("app.firebase_store.encrypt_credential", side_effect=lambda v, p: f"enc_{v}")
    @patch("app.firebase_store._user_ref")
    def test_add_zerodha_account_duplicate_raises(self, mock_ref_fn, mock_enc):
        doc = _mock_doc(exists=True, data={"zerodha_accounts": [{"account_name": "Dup"}]})
        ref = Mock()
        ref.get.return_value = doc
        mock_ref_fn.return_value = ref
        with self.assertRaises(ValueError):
            fs.add_zerodha_account("g1", "Dup", "k", "s", pin="pin123")

    @patch("app.firebase_store._user_ref")
    def test_remove_zerodha_account_success(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={"zerodha_accounts": [{"account_name": "Keep"}, {"account_name": "Remove"}]})
        ref = Mock()
        ref.get.return_value = doc
        mock_ref_fn.return_value = ref
        fs.remove_zerodha_account("g1", "Remove")
        accounts = ref.update.call_args[0][0]["zerodha_accounts"]
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["account_name"], "Keep")

    @patch("app.firebase_store._user_ref")
    def test_remove_zerodha_account_not_found(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={"zerodha_accounts": [{"account_name": "Other"}]})
        ref = Mock()
        ref.get.return_value = doc
        mock_ref_fn.return_value = ref
        with self.assertRaises(ValueError):
            fs.remove_zerodha_account("g1", "Missing")

    @patch("app.firebase_store._user_ref")
    def test_get_zerodha_account_names(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={"zerodha_accounts": [{"account_name": "A"}, {"account_name": "B"}]})
        mock_ref_fn.return_value = _mock_ref(doc)
        names = fs.get_zerodha_account_names("g1")
        self.assertEqual(names, ["A", "B"])

    @patch("app.firebase_store._user_ref")
    def test_get_zerodha_account_names_empty(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={})
        mock_ref_fn.return_value = _mock_ref(doc)
        names = fs.get_zerodha_account_names("g1")
        self.assertEqual(names, [])

    @patch("app.firebase_store.decrypt_credential", side_effect=lambda v, p: f"dec_{v}")
    @patch("app.firebase_store._user_ref")
    def test_get_zerodha_accounts_with_pin(self, mock_ref_fn, mock_dec):
        doc = _mock_doc(
            exists=True,
            data={
                "zerodha_accounts": [
                    {"account_name": "A", "api_key": "ek", "api_secret": "es"},
                ]
            },
        )
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_zerodha_accounts("g1", pin="pin123")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "A")
        self.assertEqual(result[0]["api_key"], "dec_ek")

    @patch("app.firebase_store._user_ref")
    def test_get_zerodha_accounts_no_pin(self, mock_ref_fn):
        result = fs.get_zerodha_accounts("g1", pin="")
        self.assertEqual(result, [])

    @patch("app.firebase_store.decrypt_credential", side_effect=Exception("bad"))
    @patch("app.firebase_store._user_ref")
    def test_get_zerodha_accounts_decrypt_error(self, mock_ref_fn, mock_dec):
        doc = _mock_doc(
            exists=True,
            data={
                "zerodha_accounts": [
                    {"account_name": "A", "api_key": "ek", "api_secret": "es"},
                ]
            },
        )
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_zerodha_accounts("g1", pin="pin123")
        self.assertEqual(result, [])  # skipped due to decrypt failure

    @patch("app.firebase_store._user_ref")
    def test_get_zerodha_accounts_no_doc(self, mock_ref_fn):
        doc = _mock_doc(exists=False)
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_zerodha_accounts("g1", pin="pin123")
        self.assertEqual(result, [])


class TestZerodhaSessions(unittest.TestCase):
    @patch("app.firebase_store._user_ref")
    def test_get_zerodha_sessions(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={"zerodha_sessions": {"A": {"access_token": "t"}}})
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_zerodha_sessions("g1")
        self.assertEqual(result, {"A": {"access_token": "t"}})

    @patch("app.firebase_store._user_ref")
    def test_get_zerodha_sessions_empty(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={})
        mock_ref_fn.return_value = _mock_ref(doc)
        result = fs.get_zerodha_sessions("g1")
        self.assertEqual(result, {})

    @patch("app.firebase_store._user_ref")
    def test_save_zerodha_sessions(self, mock_ref_fn):
        ref = Mock()
        mock_ref_fn.return_value = ref
        sessions = {"A": {"access_token": "t", "expiry": "2025-01-01"}}
        fs.save_zerodha_sessions("g1", sessions)
        ref.update.assert_called_once_with({"zerodha_sessions": sessions})

    @patch("app.firebase_store._user_ref")
    def test_clear_zerodha_sessions(self, mock_ref_fn):
        ref = Mock()
        mock_ref_fn.return_value = ref
        fs.clear_zerodha_sessions("g1")
        ref.update.assert_called_once()


class TestPINManagement(unittest.TestCase):
    @patch("app.firebase_store._user_ref")
    def test_has_pin_true(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={"pin_check": "some_token"})
        mock_ref_fn.return_value = _mock_ref(doc)
        self.assertTrue(fs.has_pin("g1"))

    @patch("app.firebase_store._user_ref")
    def test_has_pin_false(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={})
        mock_ref_fn.return_value = _mock_ref(doc)
        self.assertFalse(fs.has_pin("g1"))

    @patch("app.firebase_store._user_ref")
    def test_has_pin_no_doc(self, mock_ref_fn):
        doc = _mock_doc(exists=False)
        mock_ref_fn.return_value = _mock_ref(doc)
        self.assertFalse(fs.has_pin("g1"))

    @patch("app.firebase_store.create_pin_check", return_value="check_token")
    @patch("app.firebase_store._user_ref")
    def test_store_pin_check(self, mock_ref_fn, mock_create):
        ref = Mock()
        mock_ref_fn.return_value = ref
        fs.store_pin_check("g1", "pin123")
        ref.update.assert_called_once_with({"pin_check": "check_token"})

    @patch("app.firebase_store.verify_pin", return_value=True)
    @patch("app.firebase_store._user_ref")
    def test_verify_user_pin_success(self, mock_ref_fn, mock_verify):
        doc = _mock_doc(exists=True, data={"pin_check": "token"})
        mock_ref_fn.return_value = _mock_ref(doc)
        self.assertTrue(fs.verify_user_pin("g1", "pin123"))

    @patch("app.firebase_store.verify_pin", return_value=False)
    @patch("app.firebase_store._user_ref")
    def test_verify_user_pin_failure(self, mock_ref_fn, mock_verify):
        doc = _mock_doc(exists=True, data={"pin_check": "token"})
        mock_ref_fn.return_value = _mock_ref(doc)
        self.assertFalse(fs.verify_user_pin("g1", "wrong"))

    @patch("app.firebase_store._user_ref")
    def test_verify_user_pin_no_token(self, mock_ref_fn):
        doc = _mock_doc(exists=True, data={})
        mock_ref_fn.return_value = _mock_ref(doc)
        self.assertFalse(fs.verify_user_pin("g1", "pin123"))

    @patch("app.firebase_store._user_ref")
    def test_reset_zerodha_data(self, mock_ref_fn):
        ref = Mock()
        mock_ref_fn.return_value = ref
        fs.reset_zerodha_data("g1")
        ref.update.assert_called_once()
        call_data = ref.update.call_args[0][0]
        self.assertIn("zerodha_accounts", call_data)
        self.assertIn("zerodha_sessions", call_data)
        self.assertIn("pin_check", call_data)


class TestDbImportError(unittest.TestCase):
    """Test _db() when firebase_admin is not installed (lines 76-77)."""

    def test_import_error_raises_runtime_error(self):
        import sys

        import app.firebase_store as fs

        # Reset the cached firestore client so _db() re-runs the import path
        original_client = fs._firestore_client
        fs._firestore_client = None
        try:
            with patch.dict(
                sys.modules,
                {
                    "firebase_admin": None,
                    "firebase_admin.credentials": None,
                    "google.cloud": None,
                    "google.cloud.firestore": None,
                },
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    fs._db()
                self.assertIn("firebase-admin is not installed", str(ctx.exception))
        finally:
            fs._firestore_client = original_client


if __name__ == "__main__":
    unittest.main()
