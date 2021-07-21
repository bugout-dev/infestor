import os
import unittest

from . import config
from . import visitors
from .operations import add_reporter
from .testcase import InfestorTestCase


class TestReporterFileVisitor(InfestorTestCase):
    def setUp(self):
        super().setUp()
        add_reporter(self.package_dir)
        self.config = config.load_config(self.config_file)

    def test_visitor(self):
        visitor = visitors.ReporterFileVisitor()
        syntax_tree = visitor.syntax_tree(
            os.path.join(self.package_dir, self.config.reporter_filepath)
        )
        syntax_tree.visit(visitor)
        self.assertEqual(visitor.HumbugConsentImportedAs, "HumbugConsent")
        self.assertEqual(visitor.HumbugConsentInstantiatedAs, "consent")
        self.assertGreater(visitor.HumbugConsentImportedAt, 0)
        self.assertGreater(
            visitor.HumbugConsentInstantiatedAt, visitor.HumbugConsentImportedAt
        )
        self.assertEqual(visitor.HumbugReporterImportedAs, "HumbugReporter")
        self.assertEqual(visitor.HumbugReporterInstantiatedAs, "reporter")
        self.assertGreater(
            visitor.HumbugReporterImportedAt, visitor.HumbugConsentImportedAt
        )
        self.assertGreater(
            visitor.HumbugReporterInstantiatedAt, visitor.HumbugReporterImportedAt
        )
        self.assertGreater(
            visitor.HumbugReporterInstantiatedAt, visitor.HumbugConsentInstantiatedAt
        )
        self.assertEqual(
            visitor.HumbugReporterConsentArgument, visitor.HumbugConsentInstantiatedAs
        )
        self.assertNotEqual(visitor.HumbugReporterTokenArgument, "")


# TODO(yhtiyar): Write some tests for PackageFileVisitor. :)
class TestPackageFileVisitor(unittest.TestCase):
    def setUp(self):
        self.source = ""


if __name__ == "__main__":
    unittest.main()
