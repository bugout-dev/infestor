"""
These are the tools infestor uses to set up a code base for automatic Humbug instrumentation.
"""
from dataclasses import asdict, dataclass
import json
import os
from typing import Any, cast, Dict, List, Optional, Tuple

from atomicwrites import atomic_write

from .version import INFESTOR_VERSION


CONFIG_FILENAME = "humbug.json"

PROJECT_NAME_KEY = "project_name"
RELATIVE_IMPORTS_KEY = "relative_imports"
REPORTER_TOKEN_KEY = "reporter_token"
REPORTER_FILEPATH_KEY = "reporter_filepath"
REPORTER_OBJECT_NAME = "reporter_object_name"

# This needs to match the reporter object in report.py.template
DEFAULT_REPORTER_OBJECT_NAME = "reporter"


@dataclass
class InfestorConfiguration:
    project_name: str

    relative_imports: bool = False
    reporter_token: Optional[str] = None
    # reporter_filepath should be a path relative to Python root
    reporter_filepath: Optional[str] = None
    reporter_object_name: str = DEFAULT_REPORTER_OBJECT_NAME


class ConfigurationError(Exception):
    """
    Raised if there is an issue with an infestor configuration file.
    """

    pass


def parse_config(
    raw_config: Dict[str, Any]
) -> Tuple[Optional[InfestorConfiguration], List[str], List[str]]:
    """
    Checks if the given configuration is valid. If it is valid, returns (True, []) else returns
    (False, [<warnings>, ...], [<error messages>, ...]).
    """
    warn_messages: List[str] = []
    error_messages: List[str] = []

    infestor_configuration: Optional[InfestorConfiguration] = None

    project_name: Optional[str] = raw_config.get(PROJECT_NAME_KEY)
    if project_name is None:
        error_messages.append("No project name specified")
        project_name = ""

    relative_imports: Optional[bool] = raw_config.get(RELATIVE_IMPORTS_KEY)
    if relative_imports is None:
        error_messages.append(
            "Configuration does not specify whether or not to use relative imports"
        )
        relative_imports = False

    reporter_token: Optional[str] = raw_config.get(REPORTER_TOKEN_KEY)
    if reporter_token is None:
        warn_messages.append(f"No reporter token found")

    reporter_filepath: Optional[str] = raw_config.get(REPORTER_FILEPATH_KEY)
    if reporter_filepath is None:
        warn_messages.append(f"No reporter filepath found")

    reporter_object_name = raw_config.get(
        REPORTER_OBJECT_NAME, DEFAULT_REPORTER_OBJECT_NAME
    )

    if not error_messages:
        infestor_configuration = InfestorConfiguration(
            project_name=project_name,
            relative_imports=relative_imports,
            reporter_token=reporter_token,
            reporter_filepath=reporter_filepath,
            reporter_object_name=reporter_object_name,
        )

    return (infestor_configuration, warn_messages, error_messages)


def load_config(
    config_file: str, print_warnings: bool = False
) -> InfestorConfiguration:
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

    return cast(InfestorConfiguration, configuration)


def save_config(config_file: str, configuration: InfestorConfiguration) -> None:
    result_configuration = asdict(configuration)
    with atomic_write(config_file, overwrite=True) as ofp:
        json.dump(result_configuration, ofp)


def default_config_file(root_directory) -> str:
    config_file = os.path.join(root_directory, CONFIG_FILENAME)
    return config_file


def set_reporter_token(config_file: str, reporter_token: str) -> InfestorConfiguration:
    configuration = load_config(config_file)
    configuration.reporter_token = reporter_token
    save_config(config_file, configuration)
    return configuration


def initialize(
    repository: str,
    project_name: str,
    relative_imports: bool = False,
    reporter_token: Optional[str] = None,
) -> InfestorConfiguration:
    """
    Initialize infestor in a given project.
    """
    config_file = default_config_file(repository)
    configuration = InfestorConfiguration(
        project_name=project_name,
        relative_imports=relative_imports,
        reporter_token=reporter_token,
        reporter_object_name="reporter",
    )
    save_config(config_file, configuration)
    return configuration


def python_root_relative_to_repository_root(repository: str, python_root: str) -> str:
    absolute_python_root = os.path.abspath(python_root)
    relative_python_root = os.path.relpath(absolute_python_root, repository)
    return relative_python_root
