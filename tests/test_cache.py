import sys
import types
import unittest

# Allow importing lib.cache without optional sheets dependencies installed.
sys.modules.setdefault("gspread", types.ModuleType("gspread"))

google_module = types.ModuleType("google")
oauth2_module = types.ModuleType("google.oauth2")
service_account_module = types.ModuleType("google.oauth2.service_account")


class _Credentials:
    @staticmethod
    def from_service_account_info(*args, **kwargs):
        return object()


service_account_module.Credentials = _Credentials
oauth2_module.service_account = service_account_module
google_module.oauth2 = oauth2_module

sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.oauth2", oauth2_module)
sys.modules.setdefault("google.oauth2.service_account", service_account_module)

from lib.cache import compute_fingerprint, compute_row_key


class CacheTests(unittest.TestCase):
    def test_hash_row_key_is_stable(self):
        row = {"a": 1, "b": "x"}
        key1 = compute_row_key(row, "hash", [])
        key2 = compute_row_key({"b": "x", "a": 1}, "hash", [])
        self.assertEqual(key1, key2)

    def test_column_row_key_uses_requested_columns(self):
        row = {"id": "123", "name": "abc"}
        key = compute_row_key(row, "columns", ["id", "name"])
        self.assertEqual(key, "123|abc")

    def test_fingerprint_changes_when_row_changes(self):
        fp1 = compute_fingerprint({"id": "1", "v": "a"})
        fp2 = compute_fingerprint({"id": "1", "v": "b"})
        self.assertNotEqual(fp1, fp2)


if __name__ == "__main__":
    unittest.main()
