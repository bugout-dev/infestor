from dataclasses import asdict
import json
import os
import shutil
import tempfile
import unittest

from . import config


class TestParseConfig(unittest.TestCase):
    maxDiff = None

    # TODO(zomglings): Test reporter_filepath invalidities.

    def test_empty_config(self):
        raw_config = {}
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 2)
        self.assertEqual(len(errors), 2)
        self.assertIsNone(configuration)

    def test_config_with_no_project_name(self):
        raw_config = {
            config.RELATIVE_IMPORTS_KEY: False,
            config.REPORTER_TOKEN_KEY: "335da960-2dc6-48b3-97a5-c23ac1495e7d",
            config.REPORTER_FILEPATH_KEY: "report.py",
            config.REPORTER_OBJECT_NAME: "reporter",
        }
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 1)
        self.assertIsNone(configuration)

    def test_config_with_no_relative_imports(self):
        raw_config = {
            config.PROJECT_NAME_KEY: "rofl",
            config.REPORTER_TOKEN_KEY: "335da960-2dc6-48b3-97a5-c23ac1495e7d",
            config.REPORTER_FILEPATH_KEY: "report.py",
            config.REPORTER_OBJECT_NAME: "reporter",
        }
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 1)
        self.assertIsNone(configuration)

    def test_valid_config(self):
        infestor_configuration = config.InfestorConfiguration(
            project_name="lol",
            relative_imports=False,
            reporter_token="335da960-2dc6-48b3-97a5-c23ac1495e7d",
            reporter_filepath="report.py",
            reporter_object_name="reporter",
        )
        raw_config = {
            config.PROJECT_NAME_KEY: infestor_configuration.project_name,
            config.RELATIVE_IMPORTS_KEY: infestor_configuration.relative_imports,
            config.REPORTER_TOKEN_KEY: infestor_configuration.reporter_token,
            config.REPORTER_FILEPATH_KEY: infestor_configuration.reporter_filepath,
            config.REPORTER_OBJECT_NAME: "reporter",
        }
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 0)
        self.assertEqual(configuration, infestor_configuration)


class TestInit(unittest.TestCase):
    def setUp(self):
        self.repository = tempfile.mkdtemp()
        self.project_name = "my-awesome-python-project"

    def tearDown(self):
        shutil.rmtree(self.repository)

    def test_initialize_infestor_once(self):
        configuration = config.initialize(self.repository, self.project_name)
        config_file = config.default_config_file(self.repository)
        self.assertTrue(os.path.isfile(config_file))
        with open(config_file, "r") as ifp:
            configuration_json = json.load(ifp)
        self.assertDictEqual(configuration_json, asdict(configuration))

    def test_initialize_infestor_twice(self):
        initial_configuration = config.initialize(
            self.repository, "lol", relative_imports=False
        )
        final_configuration = config.initialize(
            self.repository, "lol", relative_imports=True
        )

        config_file = config.default_config_file(self.repository)
        self.assertTrue(os.path.isfile(config_file))
        with open(config_file, "r") as ifp:
            configuration_json = json.load(ifp)

        self.assertDictEqual(configuration_json, asdict(final_configuration))


if __name__ == "__main__":
    unittest.main()
