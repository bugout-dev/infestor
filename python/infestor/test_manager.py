import uuid
import unittest

from .config import InfestorConfiguration
from . import manager


class TestGetReporterImportInformationFromComplexConfiguration(unittest.TestCase):
    def setUp(self):
        self.repository = "test_project"
        self.submodule_path = "test_project/some_subpackage/some_submodule.py"
        self.reporter_object_name = "the_coolest_reporter"

        self.nonrelative_configuration = InfestorConfiguration(
            project_name="test_project",
            relative_imports=False,
            reporter_token=str(uuid.uuid4()),
            reporter_filepath="test_project/utils/reporter.py",
            reporter_object_name=self.reporter_object_name,
        )
        self.relative_configuration = InfestorConfiguration(
            project_name="test_project",
            relative_imports=True,
            reporter_token=str(uuid.uuid4()),
            reporter_filepath="test_project/utils/reporter.py",
            reporter_object_name=self.reporter_object_name,
        )

    def test_reporter_import_information_from_nonrelative_configuration(self):
        (
            reporter_import_path,
            is_relative,
            reporter_object_name,
        ) = manager.get_reporter_import_information(
            self.repository, self.submodule_path, self.nonrelative_configuration
        )
        self.assertEqual(reporter_import_path, "test_project.utils.reporter")
        self.assertFalse(is_relative)
        self.assertEqual(reporter_object_name, self.reporter_object_name)

    def test_reporter_import_information_from_relative_configuration(self):
        (
            reporter_import_path,
            is_relative,
            reporter_object_name,
        ) = manager.get_reporter_import_information(
            self.repository, self.submodule_path, self.relative_configuration
        )
        self.assertEqual(reporter_import_path, "..utils.reporter")
        self.assertTrue(is_relative)
        self.assertEqual(reporter_object_name, self.reporter_object_name)


if __name__ == "__main__":
    unittest.main()
