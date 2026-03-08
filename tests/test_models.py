import json
import unittest

from lib.models import row_to_project


class ModelCompatibilityTests(unittest.TestCase):
    def test_row_to_project_handles_legacy_fields(self):
        row = {
            "id": "proj-1",
            "status": "archived",
            "last_run_rows_failed": "3",
            "config_json": json.dumps(
                {
                    "name": "Legacy",
                    "csv_url": "https://example.com/data.csv",
                    "poll_interval_minutes": 15,
                    "keep_cache_on_relink": True,
                    "model": "gpt-5.2",
                }
            ),
        }

        project = row_to_project(row)

        self.assertEqual(project.id, "proj-1")
        self.assertTrue(project.archived)
        self.assertEqual(project.last_run_rows_errored, 3)
        self.assertEqual(project.config.name, "Legacy")
        self.assertEqual(project.config.csv_url, "https://example.com/data.csv")
        self.assertEqual(project.config.model, "gpt-5.2")


if __name__ == "__main__":
    unittest.main()
