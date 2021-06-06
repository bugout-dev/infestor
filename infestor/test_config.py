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
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 0)
        self.assertDictEqual(configuration, {})

    def test_config_with_key_different_from_python_root(self):
        raw_config = {
            "./lol": {
                config.PYTHON_ROOT_KEY: "./rofl",
                config.PROJECT_NAME_KEY: "lol",
                config.RELATIVE_IMPORTS_KEY: False,
                config.REPORTER_TOKEN_KEY: "335da960-2dc6-48b3-97a5-c23ac1495e7d",
                config.REPORTER_FILEPATH_KEY: "report.py",
            }
        }
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 1)
        self.assertDictEqual(configuration, {})

    def test_config_with_no_project_name(self):
        raw_config = {
            "./rofl": {
                config.PYTHON_ROOT_KEY: "./rofl",
                config.RELATIVE_IMPORTS_KEY: False,
                config.REPORTER_TOKEN_KEY: "335da960-2dc6-48b3-97a5-c23ac1495e7d",
                config.REPORTER_FILEPATH_KEY: "report.py",
            }
        }
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 1)
        self.assertDictEqual(configuration, {})

    def test_config_with_no_relative_imports(self):
        raw_config = {
            "./rofl": {
                config.PYTHON_ROOT_KEY: "./rofl",
                config.PROJECT_NAME_KEY: "rofl",
                config.REPORTER_TOKEN_KEY: "335da960-2dc6-48b3-97a5-c23ac1495e7d",
                config.REPORTER_FILEPATH_KEY: "report.py",
            }
        }
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 1)
        self.assertDictEqual(configuration, {})

    def test_config_with_no_python_root_or_project_name(self):
        raw_config = {
            "./rofl": {
                config.RELATIVE_IMPORTS_KEY: False,
                config.REPORTER_TOKEN_KEY: "335da960-2dc6-48b3-97a5-c23ac1495e7d",
                config.REPORTER_FILEPATH_KEY: "report.py",
            }
        }
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 2)
        self.assertDictEqual(configuration, {})

    def test_single_valid_config(self):
        infestor_configuration = config.InfestorConfiguration(
            python_root="./lol",
            project_name="lol",
            relative_imports=False,
            reporter_token="335da960-2dc6-48b3-97a5-c23ac1495e7d",
            reporter_filepath="report.py",
        )
        raw_config = {
            infestor_configuration.python_root: {
                config.PYTHON_ROOT_KEY: infestor_configuration.python_root,
                config.PROJECT_NAME_KEY: infestor_configuration.project_name,
                config.RELATIVE_IMPORTS_KEY: infestor_configuration.relative_imports,
                config.REPORTER_TOKEN_KEY: infestor_configuration.reporter_token,
                config.REPORTER_FILEPATH_KEY: infestor_configuration.reporter_filepath,
            }
        }
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 0)
        self.assertDictEqual(
            configuration, {infestor_configuration.python_root: infestor_configuration}
        )

    def test_two_valid_configs(self):
        infestor_configuration_0 = config.InfestorConfiguration(
            python_root="./lol",
            project_name="lol",
            relative_imports=False,
            reporter_token="335da960-2dc6-48b3-97a5-c23ac1495e7d",
            reporter_filepath="report.py",
        )
        infestor_configuration_1 = config.InfestorConfiguration(
            python_root="./rofl",
            project_name="rofl",
            relative_imports=False,
            reporter_token="435da960-2dc6-48b3-97a5-c23ac1495e7d",
            reporter_filepath="report.py",
        )

        raw_config = {
            infestor_configuration_0.python_root: {
                config.PYTHON_ROOT_KEY: infestor_configuration_0.python_root,
                config.PROJECT_NAME_KEY: infestor_configuration_0.project_name,
                config.RELATIVE_IMPORTS_KEY: infestor_configuration_0.relative_imports,
                config.REPORTER_TOKEN_KEY: infestor_configuration_0.reporter_token,
                config.REPORTER_FILEPATH_KEY: infestor_configuration_0.reporter_filepath,
            },
            infestor_configuration_1.python_root: {
                config.PYTHON_ROOT_KEY: infestor_configuration_1.python_root,
                config.PROJECT_NAME_KEY: infestor_configuration_1.project_name,
                config.RELATIVE_IMPORTS_KEY: infestor_configuration_1.relative_imports,
                config.REPORTER_TOKEN_KEY: infestor_configuration_1.reporter_token,
                config.REPORTER_FILEPATH_KEY: infestor_configuration_1.reporter_filepath,
            },
        }
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 0)
        self.assertDictEqual(
            configuration,
            {
                infestor_configuration_0.python_root: infestor_configuration_0,
                infestor_configuration_1.python_root: infestor_configuration_1,
            },
        )

    def test_valid_and_invalid_configs(self):
        infestor_configuration_0 = config.InfestorConfiguration(
            python_root="./lol",
            project_name="lol",
            relative_imports=False,
            reporter_token="335da960-2dc6-48b3-97a5-c23ac1495e7d",
            reporter_filepath="report.py",
        )
        infestor_configuration_1 = config.InfestorConfiguration(
            python_root="./rofl",
            project_name="rofl",
            relative_imports=False,
            reporter_token="435da960-2dc6-48b3-97a5-c23ac1495e7d",
            reporter_filepath="report.py",
        )

        raw_config = {
            infestor_configuration_0.python_root: {
                config.PYTHON_ROOT_KEY: infestor_configuration_0.python_root,
                config.PROJECT_NAME_KEY: infestor_configuration_0.project_name,
                config.RELATIVE_IMPORTS_KEY: infestor_configuration_0.relative_imports,
                config.REPORTER_TOKEN_KEY: infestor_configuration_0.reporter_token,
                config.REPORTER_FILEPATH_KEY: infestor_configuration_0.reporter_filepath,
            },
            f"{infestor_configuration_1.python_root}/": {
                config.PYTHON_ROOT_KEY: infestor_configuration_1.python_root,
                config.PROJECT_NAME_KEY: infestor_configuration_1.project_name,
                config.REPORTER_TOKEN_KEY: infestor_configuration_1.reporter_token,
                config.REPORTER_FILEPATH_KEY: infestor_configuration_1.reporter_filepath,
            },
        }
        configuration, warnings, errors = config.parse_config(raw_config)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 2)
        self.assertDictEqual(
            configuration,
            {
                infestor_configuration_0.python_root: infestor_configuration_0,
            },
        )


class TestInit(unittest.TestCase):
    def setUp(self):
        self.repository = tempfile.mkdtemp()
        self.project_name = "my-awesome-python-project"

    def tearDown(self):
        shutil.rmtree(self.repository)

    def test_initialize_infestor_once(self):
        config.initialize(self.repository, self.repository, self.project_name)
        config_file = config.default_config_file(self.repository)
        self.assertTrue(os.path.isfile(config_file))
        with open(config_file, "r") as ifp:
            configuration = json.load(ifp)

        configuration_key = config.python_root_relative_to_repository_root(
            self.repository,
            self.repository,
        )
        self.assertIsNotNone(configuration.get(configuration_key))

        self.assertEqual(len(configuration), 1)

    def test_initialize_infestor_twice(self):
        package_0 = os.path.join(self.repository, "lol")
        os.mkdir(package_0)
        package_1 = os.path.join(self.repository, "rofl")
        os.mkdir(package_1)

        config.initialize(self.repository, package_0, "lol")
        config.initialize(self.repository, package_1, "rofl")

        config_file = config.default_config_file(self.repository)
        self.assertTrue(os.path.isfile(config_file))
        with open(config_file, "r") as ifp:
            configuration = json.load(ifp)

        self.assertIsNotNone(configuration.get("lol"))
        self.assertIsNotNone(configuration.get("rofl"))

        self.assertEqual(len(configuration), 2)

    def test_initialize_infestor_twice_with_same_python_root(self):
        package_0 = os.path.join(self.repository, "lol")
        os.mkdir(package_0)
        config.initialize(self.repository, package_0, "lol", relative_imports=False)
        config.initialize(self.repository, package_0, "lol", relative_imports=True)

        config_file = config.default_config_file(self.repository)
        self.assertTrue(os.path.isfile(config_file))
        with open(config_file, "r") as ifp:
            configuration = json.load(ifp)

        self.assertIsNotNone(configuration.get("lol"))
        self.assertEqual(len(configuration), 1)
        self.assertTrue(configuration["lol"][config.RELATIVE_IMPORTS_KEY])


if __name__ == "__main__":
    unittest.main()
