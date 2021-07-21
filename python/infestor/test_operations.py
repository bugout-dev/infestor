import json
import os
import unittest
import libcst as cst
from . import operations
from . import visitors
from .testcase import InfestorTestCase


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

        reporter_filepath = os.path.join(
            self.package_dir, operations.DEFAULT_REPORTER_FILENAME
        )
        self.assertFalse(os.path.exists(reporter_filepath))

        operations.add_reporter(self.package_dir)

        with open(self.config_file, "r") as ifp:
            infestor_json_new = json.load(ifp)
        self.assertEqual(infestor_json_new["reporter_filepath"], reporter_filepath)
        self.assertTrue(os.path.exists(reporter_filepath))

        reporter_visitor = visitors.ReporterFileVisitor()
        reporter_syntax_tree = reporter_visitor.syntax_tree(reporter_filepath)

        reporter_syntax_tree.visit(reporter_visitor)

        self.assertEqual(reporter_visitor.HumbugConsentImportedAs, "HumbugConsent")
        self.assertLess(
            reporter_visitor.HumbugConsentImportedAt,
            reporter_visitor.HumbugConsentInstantiatedAt,
        )
        self.assertLess(
            reporter_visitor.HumbugReporterImportedAt,
            reporter_visitor.HumbugReporterInstantiatedAt,
        )
        self.assertEqual(
            reporter_visitor.HumbugReporterConsentArgument,
            reporter_visitor.HumbugConsentInstantiatedAs,
        )
        self.assertEqual(
            reporter_visitor.HumbugReporterTokenArgument,
            f"\"{infestor_json_new['reporter_token']}\"",
        )

    def test_system_report_add_with_no_reporter_added(self):
        with self.assertRaises(operations.GenerateReporterError):
            operations.add_call(
                operations.CALL_TYPE_SYSTEM_REPORT,
                self.package_dir,
            )

    def test_list_system_reports_for_package_with_no_system_reports(self):
        operations.add_reporter(self.package_dir)
        results = operations.list_calls(
            operations.CALL_TYPE_SYSTEM_REPORT,
            self.package_dir,
        )
        self.assertDictEqual(results, {})

    def test_decorator_list_with_no_reporter_decorators(self):
        operations.add_reporter(self.package_dir)
        results = operations.list_decorators(
            operations.DECORATOR_TYPE_RECORD_ERRORS, self.package_dir
        )
        self.assertDictEqual(results, {})

    def test_decorator_add_remove(self):
        operations.add_reporter(self.package_dir)
        target_file = os.path.join(self.package_dir, "cli.py")
        candidates = operations.decorator_candidates(
            operations.DECORATOR_TYPE_RECORD_ERRORS, self.package_dir, target_file
        )
        self.assertNotEqual(len(candidates), 0, "Failed to find decorator candidates")
        linenos = []
        for candidate in candidates:
            linenos.append(candidate.lineno)

        operations.add_decorators(
            operations.DECORATOR_TYPE_RECORD_ERRORS,
            self.package_dir,
            target_file,
            linenos,
        )

        new_candidates = operations.decorator_candidates(
            operations.DECORATOR_TYPE_RECORD_ERRORS, self.package_dir, target_file
        )

        self.assertEqual(len(new_candidates), 0, "Failed to decorate all candidates")

        decorators = operations.list_decorators(
            operations.DECORATOR_TYPE_RECORD_ERRORS, self.package_dir, [target_file]
        )

        self.assertNotEqual(decorators, {}, "Failed to list decorators")

        self.assertEqual(
            len(decorators[target_file]),
            len(candidates),
            "Failed to list all decorators",
        )

        linenos = []
        for decorator in decorators[target_file]:
            linenos.append(decorator.lineno)

        operations.remove_decorators(
            operations.DECORATOR_TYPE_RECORD_ERRORS,
            self.package_dir,
            target_file,
            linenos,
        )

        decorators = operations.list_decorators(
            operations.DECORATOR_TYPE_RECORD_ERRORS, self.package_dir, [target_file]
        )

        self.assertEqual(decorators, {}, "Failed to remove decorators")

    def test_system_report_add(self):
        operations.add_reporter(self.package_dir)
        operations.add_call(operations.CALL_TYPE_SYSTEM_REPORT, self.package_dir)

        target_file = os.path.join(self.package_dir, "__init__.py")

        source = ""
        with open(target_file, "r") as ifp:
            for line in ifp:
                source += line

        source_tree = cst.metadata.MetadataWrapper(cst.parse_module(source))
        visitor = visitors.PackageFileVisitor(self.package_name + ".report", False)
        source_tree.visit(visitor)

        self.assertNotEqual(visitor.ReporterImportedAt, -1, "reporter not imported")

        self.assertNotEqual(
            len(visitor.calls.get("system_report")), 0, "system_call not called"
        )

        self.assertEqual(
            visitor.last_import_lineno,
            visitor.ReporterImportedAt,
            "reporter is not last import",
        )
        self.assertTrue(
            visitor.ReporterCorrectlyImported,
            "reporter is not imported right after last naked import",
        )
        self.assertEqual(
            visitor.ReporterImportedAt,
            visitor.calls.get("system_report")[0].lineno - 1,
            "system_call is not called right after import",
        )

    def test_system_report_remove(self):
        operations.add_reporter(self.package_dir)
        operations.add_call(operations.CALL_TYPE_SYSTEM_REPORT, self.package_dir)
        calls = operations.list_calls(
            operations.CALL_TYPE_SYSTEM_REPORT, self.package_dir
        )
        self.assertNotEqual(calls, {}, "Failed to add system_report call")

        operations.remove_calls(operations.CALL_TYPE_SYSTEM_REPORT, self.package_dir)
        calls = operations.list_calls(
            operations.CALL_TYPE_SYSTEM_REPORT, self.package_dir
        )
        self.assertEqual(calls, {}, "Failed to remove system_report call")


if __name__ == "__main__":
    unittest.main()
