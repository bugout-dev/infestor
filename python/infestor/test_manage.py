import glob
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid

import pygit2

from . import commit, config, manage


class TestSetupReporter(unittest.TestCase):
    def setUp(self):
        self.repository = tempfile.mkdtemp()
        pygit2.init_repository(self.repository, False)

        self.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")

        script_basename = "a_script.py"
        script_file_fixture = os.path.join(self.fixtures_dir, script_basename)
        self.script_file = os.path.join(self.repository, script_basename)
        shutil.copyfile(script_file_fixture, self.script_file)

        package_basename = "a_package"
        package_dir_fixture = os.path.join(self.fixtures_dir, package_basename)
        self.package_dir = os.path.join(self.repository, package_basename)
        shutil.copytree(package_dir_fixture, self.package_dir)

        package_files = [
            os.path.relpath(python_file, start=self.repository)
            for python_file in glob.glob(os.path.join(self.package_dir, "*.py"))
        ]
        commit.commit_files(
            self.repository,
            "refs/heads/master",
            [script_basename, *package_files],
            "initial commit",
        )

        self.reporter_token = str(uuid.uuid4())

    def tearDown(self) -> None:
        DEBUG = os.getenv("DEBUG")
        if DEBUG != "1":
            shutil.rmtree(self.repository)
        else:
            print(
                f"DEBUG=1: Retaining test directory - {self.repository}",
                file=sys.stderr,
            )

    def test_add_reporter_for_package(self):
        config.initialize(
            self.repository,
            self.package_dir,
            "a_package",
            reporter_token=self.reporter_token,
        )
        self.assertTrue(
            os.path.exists(os.path.join(self.repository, config.CONFIG_FILENAME))
        )

        manage.add_reporter(self.repository, self.package_dir)

        infestor_json_path = config.default_config_file(self.repository)
        self.assertTrue(os.path.exists(infestor_json_path))
        with open(infestor_json_path, "r") as ifp:
            infestor_json = json.load(ifp)

        expected_config_json = {
            "a_package": {
                "python_root": "a_package",
                "project_name": "a_package",
                "relative_imports": False,
                "reporter_token": self.reporter_token,
                "reporter_filepath": "report.py",
            }
        }
        self.assertDictEqual(infestor_json, expected_config_json)

        self.assertTrue(
            os.path.exists(
                os.path.join(
                    self.repository,
                    self.package_dir,
                    "report.py",
                )
            )
        )

    def test_list_system_reports_for_package_with_no_system_reports(self):
        config.initialize(
            self.repository, self.package_dir, os.path.basename(self.package_dir)
        )
        results = manage.list_calls(
            manage.CALL_TYPE_SYSTEM_REPORT,
            self.repository,
            os.path.basename(self.package_dir),
        )
        self.assertDictEqual(results, {})


if __name__ == "__main__":
    unittest.main()
