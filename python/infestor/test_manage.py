import glob
import json
import os
import shutil
import sys
import tempfile
from typing import Optional
import unittest
import uuid

import libcst as cst
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

        self.package_name = "a_package"

        self.reporter_token = str(uuid.uuid4())

        config.initialize(
            self.repository,
            self.package_dir,
            self.package_name,
            reporter_token=self.reporter_token,
        )

        self.config_file = config.default_config_file(self.repository)

        package_files = [
            os.path.relpath(python_file, start=self.repository)
            for python_file in glob.glob(os.path.join(self.package_dir, "*.py"))
        ]
        commit.commit_files(
            self.repository,
            "refs/heads/master",
            [script_basename, *package_files, config.CONFIG_FILENAME],
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

    def test_add_reporter_for_package(self):
        # Steps:
        # 1. Initialize infestor config in given repository, with Python package as target.
        # 2. Add reporter to package
        # 3. Check that reporter file did not exist before reporter was added, but that it DOES exist afterwards.
        # 4. Check that structure of reporter file contains:
        #    a. Import of HumbugConsent from humbug.consent
        #    b. Import of HumbugReporter from humbug.reporter
        #    c. Instantiation of HumbugConsent into a variable (store the name of this variable)
        #    d. Instantiation of HumbugReporter with consent variable as an argument
        #    e. Instantiation of HumbugReporter with the configured token as an argument
        with open(self.config_file, "r") as ifp:
            infestor_json_old = json.load(ifp)
        self.assertIsNone(infestor_json_old[self.package_name]["reporter_filepath"])

        reporter_filepath = os.path.join(self.repository, self.package_dir, "report.py")
        self.assertFalse(os.path.exists(reporter_filepath))

        manage.add_reporter(self.repository, self.package_dir)

        with open(self.config_file, "r") as ifp:
            infestor_json_new = json.load(ifp)
        self.assertEqual(
            infestor_json_new[self.package_name]["reporter_filepath"], "report.py"
        )
        self.assertTrue(os.path.exists(reporter_filepath))

        with open(reporter_filepath, "r") as ifp:
            reporter_source = cst.metadata.MetadataWrapper(cst.parse_module(ifp.read()))

        class TestVisitor(cst.CSTVisitor):
            METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

            def __init__(self):
                self.HumbugConsentImportedAs: str = ""
                self.HumbugConsentImportedAt: int = -1
                self.HumbugReporterImportedAs: str = ""
                self.HumbugReporterImportedAt: int = -1
                self.HumbugConsentInstantiatedAt: int = -1
                self.HumbugConsentInstantiatedAs: str = ""
                self.HumbugReporterInstantiatedAt: int = -1
                self.HumbugReporterConsentArgument: str = ""
                self.HumbugReporterTokenArgument: str = ""

            def visit_ImportFrom(self, node: cst.ImportFrom) -> Optional[bool]:
                position = self.get_metadata(cst.metadata.PositionProvider, node)
                if (
                    isinstance(node.module, cst.Attribute)
                    and node.module.value.value == "humbug"
                ):
                    if node.module.attr.value == "consent":
                        for name in node.names:
                            if name.name.value == "HumbugConsent":
                                self.HumbugConsentImportedAs = "HumbugConsent"

                                if name.asname is not None:
                                    self.HumbugConsentImportedAs = name.asname.value

                                self.HumbugConsentImportedAt = position.start.line
                    elif node.module.attr.value == "report":
                        for name in node.names:
                            if name.name.value == "HumbugReporter":
                                self.HumbugReporterImportedAs = "HumbugReporter"

                                if name.asname is not None:
                                    self.HumbugReporterImportedAs = name.asname.value

                                self.HumbugReporterImportedAt = position.start.line

                return False

            def visit_Assign(self, node: cst.Assign) -> Optional[bool]:
                # TODO: come back
                if (
                    len(node.targets) == 1
                    and isinstance(node.value, cst.Call)
                    and node.value.func.value == self.HumbugConsentImportedAs
                ):
                    position = self.get_metadata(cst.metadata.PositionProvider, node)
                    self.HumbugConsentInstantiatedAt = position.start.line
                    self.HumbugConsentInstantiatedAs = node.targets[0].target.value
                    return False
                return True

            def visit_Call(self, node: cst.Call) -> Optional[bool]:
                if (
                    isinstance(node.func, cst.Name)
                    and node.func.value == self.HumbugReporterImportedAs
                ):
                    position = self.get_metadata(cst.metadata.PositionProvider, node)
                    self.HumbugReporterInstantiatedAt = position.start.line
                    for arg in node.args:
                        if arg.keyword.value == "consent":
                            self.HumbugReporterConsentArgument = arg.value.value
                        elif arg.keyword.value == "bugout_token":
                            self.HumbugReporterTokenArgument = arg.value.value
                return False

        visitor = TestVisitor()
        reporter_source.visit(visitor)

        self.assertEqual(visitor.HumbugConsentImportedAs, "HumbugConsent")
        self.assertLess(
            visitor.HumbugConsentImportedAt, visitor.HumbugConsentInstantiatedAt
        )
        self.assertLess(
            visitor.HumbugReporterImportedAt, visitor.HumbugReporterInstantiatedAt
        )
        self.assertEqual(
            visitor.HumbugReporterConsentArgument, visitor.HumbugConsentInstantiatedAs
        )
        self.assertEqual(
            visitor.HumbugReporterTokenArgument,
            f"\"{infestor_json_new[self.package_name]['reporter_token']}\"",
        )

    def test_system_report_add_with_no_reporter_added(self):
        with self.assertRaises(manage.GenerateReporterError):
            manage.add_call(
                manage.CALL_TYPE_SYSTEM_REPORT,
                self.repository,
                os.path.relpath(self.package_dir, self.repository),
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
