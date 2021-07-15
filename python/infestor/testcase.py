import enum
import glob
import os
import shutil
import sys
import tempfile
import unittest
import uuid

import pygit2

from . import commit
from . import config


class InfestorTestCase(unittest.TestCase):
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

        self.package_name = "a_package"

        self.reporter_token = str(uuid.uuid4())

        self.config = config.initialize(
            self.package_dir,
            self.package_name,
            reporter_token=self.reporter_token,
        )

        self.config_file = config.default_config_file(self.package_dir)

        package_files = [
            os.path.relpath(python_file, start=self.repository)
            for python_file in glob.glob(os.path.join(self.package_dir, "*.py"))
        ]
        commit.commit_files(
            self.repository,
            "refs/heads/master",
            [
                script_basename,
                *package_files,
                os.path.join(package_basename, config.CONFIG_FILENAME),
            ],
            "initial commit",
        )

    def tearDown(self) -> None:
        DEBUG = os.getenv("DEBUG")
        if DEBUG != "1":
            shutil.rmtree(self.repository)
        else:
            print(
                f"DEBUG=1: Retaining test directory - {self.repository}",
                file=sys.stderr,
            )
