import glob
import json
import os
import shutil
import sys
import tempfile
from typing import Optional, Sequence, List, Tuple, Union
import unittest
import uuid

import libcst as cst
import libcst.matchers as m
import pygit2

from . import commit, config, manage


class ReporterFileVisitor(cst.CSTVisitor):
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
        position = self.get_metadata(cst.metadata.PositionProvider, node)  # type: ignore
        if (
                isinstance(node.module, cst.Attribute)
                and isinstance(node.module.value, cst.Name)
                and node.module.value.value == "humbug"
        ):
            if node.module.attr.value == "consent" and not isinstance(
                    node.names, cst.ImportStar
            ):
                for name in node.names:
                    if name.name.value == "HumbugConsent":
                        self.HumbugConsentImportedAs = "HumbugConsent"

                        if name.asname is not None and isinstance(
                                name.asname, cst.Name
                        ):
                            self.HumbugConsentImportedAs = name.asname.value

                        self.HumbugConsentImportedAt = position.start.line
            elif node.module.attr.value == "report" and not isinstance(
                    node.names, cst.ImportStar
            ):
                for name in node.names:
                    if name.name.value == "HumbugReporter":
                        self.HumbugReporterImportedAs = "HumbugReporter"

                        if name.asname is not None and isinstance(
                                name.asname, cst.Name
                        ):
                            self.HumbugReporterImportedAs = name.asname.value

                        self.HumbugReporterImportedAt = position.start.line

        return False

    def visit_Assign(self, node: cst.Assign) -> Optional[bool]:
        # TODO: come back
        if (
                len(node.targets) == 1
                and isinstance(node.value, cst.Call)
                and isinstance(node.value.func, cst.Name)
                and isinstance(node.targets[0].target, cst.Name)
                and node.value.func.value == self.HumbugConsentImportedAs
        ):
            position = self.get_metadata(cst.metadata.PositionProvider, node)  # type: ignore
            self.HumbugConsentInstantiatedAt = position.start.line
            self.HumbugConsentInstantiatedAs = node.targets[0].target.value
            return False
        return True

    def visit_Call(self, node: cst.Call) -> Optional[bool]:
        if (
                isinstance(node.func, cst.Name)
                and node.func.value == self.HumbugReporterImportedAs
        ):
            position = self.get_metadata(cst.metadata.PositionProvider, node)  # type: ignore
            self.HumbugReporterInstantiatedAt = position.start.line
            for arg in node.args:
                if (
                        arg.keyword is not None
                        and arg.keyword.value == "consent"
                        and isinstance(arg.value, cst.Name)
                ):
                    self.HumbugReporterConsentArgument = arg.value.value
                elif (
                        arg.keyword is not None
                        and arg.keyword.value == "bugout_token"
                        and isinstance(arg.value, cst.SimpleString)
                ):
                    self.HumbugReporterTokenArgument = arg.value.value
        return False


REPORTER_MODULE_NAME = manage.DEFAULT_REPORTER_FILENAME[:-3]  # removing .py ending


class PackageFileVisitor(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)
    last_import_lineno = 0

    def __init__(self, reporter_module_path: str, relative_imports: bool):
        self.ReporterImportedAs: str = ""
        self.ReporterImportedAt: int = -1
        self.ReporterSystemCallAt: int = -1
        self.ReporterExcepthookAt: int = -1
        self.ReporterCorrectlyImported: bool = False

        self.relative_imports = relative_imports
        self.reporter_module_path = reporter_module_path

    def visit_FunctionDef(self, node: cst.FunctionDef):
        return False

    def visit_ClassDef(self, node: cst.ClassDef):
        return False

    def matches_with_package_import(self, node: cst.ImportFrom):
        return m.matches(
            node.module,
            m.Attribute(
                value=m.Name(
                    value=self.reporter_module_path
                ),
                attr=m.Name(
                    value="report"
                ),
            ),
        )

    def matches_system_report_call(self, node: cst.Call):
        return m.matches(
            node,
            m.Call(
                func=m.Attribute(
                    value=m.Name(
                        value=self.ReporterImportedAs
                    ),
                    attr=m.Name(
                        value="system_report"  # manage
                    ),
                ),
            ),
        )

    def check_imports(self, node: Union[cst.Import, cst.ImportFrom]):
        module = node.module.value
        position = self.get_metadata(cst.metadata.PositionProvider, node)
        import_aliases = node.names
        if self.relative_imports:
            expected_level = 0
            for character in self.reporter_module_path:
                if character == ".":
                    expected_level += 1
                else:
                    break
            node_import_level = 0
            for dot in node.relative:
                if isinstance(dot, cst.Dot):
                    node_import_level += 1
                else:
                    break
            if (
                    node_import_level == expected_level
                    and module == self.reporter_module_path[expected_level:]
            ):
                for alias in import_aliases:
                    name = alias.name.value
                    if name == "reporter":
                        asname = alias.asname
                        if asname:
                            self.ReporterImportedAs = asname.name.value
                        else:
                            self.ReporterImportedAs = name
                        self.ReporterImportedAt = position.start.line
                        self.ReporterCorrectlyImported = position.start.line == self.last_import_lineno + 1

        elif module.value == self.reporter_module_path:
            for alias in import_aliases:
                name = alias.name.value
                if name == "reporter":
                    asname = alias.asname
                    if asname:
                        self.ReporterImportedAs = asname.name.value
                    else:
                        self.ReporterImportedAs = name
                    self.ReporterImportedAt = position.start.line
                    self.ReporterCorrectlyImported = position.start.line == self.last_import_lineno + 1

        self.last_import_lineno = position.end.line

    def visit_Import(self, node: cst.Import) -> Optional[bool]:
        self.check_imports(node)

    def visit_ImportFrom(self, node: cst.ImportFrom) -> Optional[bool]:
        self.check_imports(node)

    def visit_Call(self, node: cst.Call) -> Optional[bool]:
        if self.ReporterImportedAt == -1:
            return
        if isinstance(node.func, cst.Attribute) and isinstance(node.func.value, cst.Name):
            name = node.func.value.value
            if (
                    name == self.ReporterImportedAs
                    and isinstance(node.func.attr, cst.Name)
                    and node.func.attr.value == manage.CALL_TYPE_SYSTEM_REPORT
            ):
                position = self.get_metadata(cst.metadata.PositionProvider, node)
                self.ReporterSystemCallAt = position.start.line


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
        self.assertIsNone(infestor_json_old["reporter_filepath"])

        reporter_filepath = os.path.join(self.package_dir, "report.py")
        self.assertFalse(os.path.exists(reporter_filepath))

        manage.add_reporter(self.package_dir)

        with open(self.config_file, "r") as ifp:
            infestor_json_new = json.load(ifp)
        self.assertEqual(infestor_json_new["reporter_filepath"], "report.py")
        self.assertTrue(os.path.exists(reporter_filepath))

        with open(reporter_filepath, "r") as ifp:
            reporter_source = cst.metadata.MetadataWrapper(cst.parse_module(ifp.read()))

        visitor = ReporterFileVisitor()
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
            f"\"{infestor_json_new['reporter_token']}\"",
        )

    def test_system_report_add_with_no_reporter_added(self):
        with self.assertRaises(manage.GenerateReporterError):
            manage.add_call(
                manage.CALL_TYPE_SYSTEM_REPORT,
                self.package_dir,
            )

    def test_list_system_reports_for_package_with_no_system_reports(self):
        results = manage.list_calls(
            manage.CALL_TYPE_SYSTEM_REPORT,
            self.package_dir,
        )
        self.assertDictEqual(results, {})

    def test_system_report_add(self):

        manage.add_reporter(self.package_dir)
        manage.add_call(manage.CALL_TYPE_SYSTEM_REPORT, self.package_dir)

        target_file = self.package_dir
        if os.path.isdir(target_file):
            target_file = os.path.join(target_file, "__init__.py")

        source = ""
        with open(target_file, "r") as ifp:
            for line in ifp:
                source += line
        source_tree = cst.metadata.MetadataWrapper(cst.parse_module(source))

        visitor = PackageFileVisitor(self.package_name, False)
        source_tree.visit(visitor)

        self.assertNotEqual(
            visitor.ReporterImportedAt,
            -1,
            "reporter not imported"
        )

        self.assertNotEqual(
            visitor.ReporterSystemCallAt,
            -1,
            "system_call not called"
        )

        self.assertEqual(
            visitor.last_import_lineno,
            visitor.ReporterImportedAt,
            "reporter is not last import"
        )
        self.assertTrue(
            visitor.ReporterCorrectlyImported,
            "reporter is not imported right after last naked import"
        )
        self.assertEqual(
            visitor.ReporterImportedAt,
            visitor.ReporterSystemCallAt - 1,
            "system_call is not called right after import"
        )


if __name__ == "__main__":
    unittest.main()
