import json
import os
from typing import Optional
import unittest

import libcst as cst
import libcst.matchers as m

from . import manage
from . import visitors
from .testcase import InfestorTestCase

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

    def matches_call(self, node: cst.Call, call_name: str):
        return m.matches(
            node,
            m.Call(
                func=m.Attribute(
                    value=m.Name(
                        value=self.ReporterImportedAs
                    ),
                    attr=m.Name(
                        value=call_name
                    ),
                ),
            ),
        )

    def matches_system_report_call(self, node: cst.Call):
        return self.matches_call(node, manage.CALL_TYPE_SYSTEM_REPORT)

    def matches_setup_excepthook(self, node: cst.Call):
        return self.matches_call(node, manage.CALL_TYPE_SETUP_EXCEPTHOOK)

    def visit_Import(self, node: cst.Import) -> Optional[bool]:
        position = self.get_metadata(cst.metadata.PositionProvider, node)
        self.last_import_lineno = position.end.line

    def check_alias_for_reporter(self, import_aliases, position):
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

    def visit_ImportFrom(self, node: cst.ImportFrom) -> Optional[bool]:
        position = self.get_metadata(cst.metadata.PositionProvider, node)
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
                    and node.module.value == self.reporter_module_path[expected_level:]
            ):
                import_aliases = node.names
                self.check_alias_for_reporter(import_aliases, position)

        elif self.matches_with_package_import(node):
            import_aliases = node.names
            self.check_alias_for_reporter(import_aliases, position)

        self.last_import_lineno = position.end.line

    def visit_Call(self, node: cst.Call) -> Optional[bool]:
        if self.ReporterImportedAt == -1:
            return
        if self.matches_system_report_call(node):
            position = self.get_metadata(cst.metadata.PositionProvider, node)
            self.ReporterSystemCallAt = position.start.line
        elif self.matches_setup_excepthook(node):
            position = self.get_metadata(cst.metadata.PositionProvider, node)
            self.ReporterExcepthookAt = position.start.line


class TestSetupReporter(InfestorTestCase):
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

        reporter_visitor = visitors.ReporterFileVisitor()
        reporter_syntax_tree = reporter_visitor.syntax_tree(reporter_filepath)

        reporter_syntax_tree.visit(reporter_visitor)

        self.assertEqual(reporter_visitor.HumbugConsentImportedAs, "HumbugConsent")
        self.assertLess(
            reporter_visitor.HumbugConsentImportedAt, reporter_visitor.HumbugConsentInstantiatedAt
        )
        self.assertLess(
            reporter_visitor.HumbugReporterImportedAt, reporter_visitor.HumbugReporterInstantiatedAt
        )
        self.assertEqual(
            reporter_visitor.HumbugReporterConsentArgument, reporter_visitor.HumbugConsentInstantiatedAs
        )
        self.assertEqual(
            reporter_visitor.HumbugReporterTokenArgument,
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
