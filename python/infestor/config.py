"""
These are the tools infestor uses to set up a code base for automatic Humbug instrumentation.
"""
from dataclasses import asdict, dataclass
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from atomicwrites import atomic_write

from .version import INFESTOR_VERSION


CONFIG_FILENAME = "infestor.json"


@dataclass
class InfestorConfiguration:
    python_root: str
    project_name: str
    relative_imports: bool = False
    reporter_token: Optional[str] = None
    # reporter_filepath should be a path relative to python_root
    reporter_filepath: Optional[str] = None


REPORTER_TOKEN_KEY = "reporter_token"
PYTHON_ROOT_KEY = "python_root"
PROJECT_NAME_KEY = "project_name"
RELATIVE_IMPORTS_KEY = "relative_imports"
REPORTER_FILEPATH_KEY = "reporter_filepath"


class ConfigurationError(Exception):
    """
    Raised if there is an issue with an infestor configuration file.
    """

    pass


def parse_config(
    raw_config: Dict[str, Dict[str, Any]]
) -> Tuple[Dict[str, InfestorConfiguration], List[str], List[str]]:
    """
    Checks if the given configuration is valid. If it is valid, returns (True, []) else returns
    (False, [<warnings>, ...], [<error messages>, ...]).
    """
    warn_messages: List[str] = []
    error_messages: List[str] = []

    parsed_config: Dict[str, InfestorConfiguration] = {}

    for key_path, subconfiguration in raw_config.items():
        python_root: Optional[str] = subconfiguration.get(PYTHON_ROOT_KEY)
        if python_root is None:
            error_messages.append(f"{key_path}: No Python root directory specified")
            python_root = ""
        elif python_root != key_path:
            error_messages.append(
                f"{key_path}: Python root directory differs from the configuration key"
            )

        project_name: Optional[str] = subconfiguration.get(PROJECT_NAME_KEY)
        if project_name is None:
            error_messages.append(f"{key_path}: No project name specified")
            project_name = ""

        relative_imports: Optional[bool] = subconfiguration.get(RELATIVE_IMPORTS_KEY)
        if relative_imports is None:
            error_messages.append(
                f"{key_path}: Configuration does not specify whether or not to use relative imports"
            )
            relative_imports = False

        reporter_token: Optional[str] = subconfiguration.get(REPORTER_TOKEN_KEY)
        if reporter_token is None:
            warn_messages.append(f"{key_path}: No reporter token found")

        reporter_filepath: Optional[str] = subconfiguration.get(REPORTER_FILEPATH_KEY)
        if reporter_filepath is None:
            warn_messages.append(f"{key_path}: No reporter filepath found")

        if not error_messages:
            infestor_configuration = InfestorConfiguration(
                python_root=python_root,
                project_name=project_name,
                relative_imports=relative_imports,
                reporter_token=reporter_token,
                reporter_filepath=reporter_filepath,
            )
            parsed_config[infestor_configuration.python_root] = infestor_configuration

    return (parsed_config, warn_messages, error_messages)


def load_config(
    config_file: str, print_warnings: bool = False
) -> Dict[str, InfestorConfiguration]:
    """
    Loads an infestor configuration from file and validates it.
    """
    try:
        with open(config_file, "r") as ifp:
            raw_config = json.load(ifp)
    except:
        raise ConfigurationError(f"Could not read configuration: {config_file}")

    configuration, warnings, errors = parse_config(raw_config)

    if print_warnings:
        warning_items = "\n".join([f"- {warning}" for warning in warnings])
        if warnings:
            print(
                f"Warnings when loading configuration file ({config_file}):\n{warning_items}"
            )

    if errors:
        error_items = "\n".join([f"- {error}" for error in errors])
        error_message = (
            f"Errors loading configuration file ({config_file}):\n{error_items}"
        )
        raise ConfigurationError(error_message)

    return configuration


def save_config(config_file: str, configuration: InfestorConfiguration) -> None:
    result_configuration: Dict[str, Any] = {}
    if os.path.exists(config_file):
        existing_configuration = load_config(config_file, print_warnings=False)
        for python_root in existing_configuration:
            result_configuration[python_root] = asdict(
                existing_configuration[python_root]
            )

    result_configuration[configuration.python_root] = asdict(configuration)
    with atomic_write(config_file, overwrite=True) as ofp:
        json.dump(result_configuration, ofp)


def default_config_file(root_directory) -> str:
    config_file = os.path.join(root_directory, CONFIG_FILENAME)

    return config_file


def set_reporter_token(
    config_file: str, python_root: str, reporter_token: str
) -> Dict[str, InfestorConfiguration]:
    config = load_config(config_file)
    config[python_root].reporter_token = reporter_token
    save_config(config_file, config[python_root])
    return config


def initialize(
    repository: str,
    python_root: str,
    project_name: str,
    relative_imports: bool = False,
    reporter_token: Optional[str] = None,
) -> None:
    """
    Initialize infestor in a given project.
    """
    config_file = default_config_file(repository)

    configuration = InfestorConfiguration(
        python_root=python_root_relative_to_repository_root(repository, python_root),
        project_name=project_name,
        relative_imports=relative_imports,
        reporter_token=reporter_token,
    )
    save_config(config_file, configuration)


def python_root_relative_to_repository_root(repository: str, python_root: str) -> str:
    absolute_python_root = os.path.abspath(python_root)
    relative_python_root = os.path.relpath(absolute_python_root, repository)
    return relative_python_root
