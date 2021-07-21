import logging
import os
from typing import cast, Dict, List, Optional, Sequence
from . import models
from .errors import *
from .manager import (
    PackageFileManager,
    DECORATOR_TYPE_RECORD_ERRORS,
    DECORATOR_TYPE_RECORD_CALL,
    CALL_TYPE_SETUP_EXCEPTHOOK,
    CALL_TYPE_SYSTEM_REPORT,
)
from .config import (
    default_config_file,
    load_config,
    save_config,
    python_root_relative_to_repository_root,
)

DEFAULT_REPORTER_FILENAME = "report.py"
DEFAULT_REPORTER_OBJECT_NAME = "reporter"
REPORTER_FILE_TEMPLATE: Optional[str] = None
TEMPLATE_FILEPATH = os.path.join(os.path.dirname(__file__), "report.py.template")

try:
    with open(TEMPLATE_FILEPATH, "r") as ifp:
        REPORTER_FILE_TEMPLATE = ifp.read()
except Exception as e:
    logging.warn(f"WARNING: Could not load reporter template from {TEMPLATE_FILEPATH}:")
    logging.warn(e)


def python_files(repository: str) -> Sequence[str]:
    results: List[str] = []
    if os.path.isfile(repository):
        return [repository]

    for dirpath, _, filenames in os.walk(repository, topdown=True):
        results.extend(
            [
                os.path.join(dirpath, filename)
                for filename in filenames
                if filename.endswith(".py")
            ]
        )

    return results


def list_calls(
    call_type: str,
    repository: str,
    candidate_files: Optional[Sequence[str]] = None,
) -> Dict[str, List[models.ReporterCall]]:
    """
    Args:
    0. call_type - Type of call to list in the given package (e.g. "system_report", "setup_excepthook", etc.)
    1. repository - Path to repository in which Infestor has been set up
    2. candidate_files - Optional list of files to restrict analysis to
    """
    results: Dict[str, List[models.ReporterCall]] = {}
    if candidate_files is None:
        candidate_files = python_files(repository)

    for filepath in candidate_files:
        package_file_manager = PackageFileManager(repository, filepath)
        calls = package_file_manager.get_calls(call_type)
        if calls:
            results[filepath] = calls

    return results


def add_call(
    call_type: str,
    repository: str,
    submodule_path: Optional[str] = None,
) -> None:
    """
    Args:
    0. call_type - Type of call to add to the given package (e.g. "system_report", "setup_excepthook", etc.)
    1. repository - Path to repository in which Infestor has been set up
    2. submodule_path: Path (relative to python_root) of file in which we want to add a sytem_report
    """
    # Determine the file to which we should add the call
    target_file = submodule_path
    if target_file is None:
        target_file = repository
        if os.path.isdir(target_file):
            target_file = os.path.join(target_file, "__init__.py")

    if not os.path.exists(target_file):
        with open(target_file, "w") as ofp:
            ofp.write("")

    package_file_manager = PackageFileManager(repository, target_file)
    package_file_manager.add_call(call_type)
    package_file_manager.write_to_file()


def remove_calls(
    call_type: str,
    repository: str,
    submodule_path: Optional[str] = None,
) -> None:
    """
    Args:
    0. call_type - Type of call to remove from the given package (e.g. "system_report", "setup_excepthook", etc.)
    1. repository - Path to repository in which Infestor has been set up
    2. submodule_path: Path (relative to python_root) of file in which we want to add a sytem_report
    """
    candidate_files: Sequence[str] = []

    if submodule_path is None:
        candidate_files = python_files(repository)
    else:
        candidate_files = [submodule_path]

    for candidate_file in candidate_files:
        package_file_manager = PackageFileManager(repository, candidate_file)
        package_file_manager.remove_call(call_type)
        package_file_manager.write_to_file()


def list_decorators(
    decorator_type: str,
    repository: str,
    candidate_files: Optional[Sequence[str]] = None,
) -> Dict[str, List[models.ReporterDecorator]]:
    """
    Args:
    0. decorator_type - Type of decorator to list in the given package (choices: "record_call", "record_error")
    1. repository - Path to repository in which Infestor has been set up
    2. python_root - Path (relative to repository) of Python package to work with (used to parse config)
    3. candidate_files - Optional list of files to restrict analysis to

    Returns a dictionary mapping file paths to functions defined in those files decorated by the given decorator_type method
    on a managed Humbug reporter.
    """
    results: Dict[str, List[models.ReporterDecorator]] = {}

    if candidate_files is None:
        candidate_files = python_files(repository)

    for candidate_file in candidate_files:
        package_file_manager = PackageFileManager(repository, candidate_file)
        decorators = package_file_manager.list_decorators(decorator_type)
        if decorators:
            results[candidate_file] = decorators

    return results


def decorator_candidates(
    decorator_type: str,
    repository: str,
    submodule_path: str,
) -> List[models.ReporterDecoratorCandidate]:
    """
    Args:
    0. decorator_type - Type of decorator to add to the given package (choices: "record_call", "record_error")
    1. repository - Path to repository in which Infestor has been set up
    2. submodule_path: Path (relative to python_root) of file in which we want to add a sytem_report

    Returns a list of tuples of the form:
    (
        <function name>,
        <function definition starting line number>
    )

    This list is the list of candidate function definitions that the user could decorate (i.e. the ones which
    do not already have a decorator of the given decorator_type).
    """
    package_file_manager = PackageFileManager(repository, submodule_path)
    return package_file_manager.decorator_candidates(decorator_type)


def add_decorators(
    decorator_type: str,
    repository: str,
    submodule_path: str,
    linenos: List[int],
) -> None:
    """
    Args:
    0. decorator_type - Type of decorator to add to the given package (choices: "record_call", "record_error")
    1. repository - Path to repository in which Infestor has been set up
    2. submodule_path: Path (relative to python_root) of file in which we want to add a sytem_report
    3. linenos: Line numbers where functions are defined that we wish to decorate
    """

    candidates = decorator_candidates(decorator_type, repository, submodule_path)

    candidate_linenos = []
    for candidate in candidates:
        candidate_linenos.append(candidate.lineno)

    for lineno in linenos:
        if lineno not in candidate_linenos:
            raise GenerateDecoratorError(
                f"Non-candidate source code: submodule_path={submodule_path}, lineno={lineno}"
            )

    package_file_manager = PackageFileManager(repository, submodule_path)
    package_file_manager.add_decorators(decorator_type, linenos)
    package_file_manager.write_to_file()


def remove_decorators(
    decorator_type: str,
    repository: str,
    submodule_path: str,
    linenos: List[int],
) -> None:
    """
    Args:
    0. decorator_type - Type of decorator to remove from the given package (choices: "record_call", "record_error")
    1. repository - Path to repository in which Infestor has been set up
    2. submodule_path: Path (relative to python_root) of file in which we want to add a sytem_report
    3. linenos: Line numbers where decorated functions are defined that we wish to undecorate
    """
    candidates_for_removal = list_decorators(
        decorator_type, repository, [submodule_path]
    ).get(submodule_path, [])

    candidate_linenos = []
    for candidate in candidates_for_removal:
        candidate_linenos.append(candidate.lineno)

    for lineno in linenos:
        if lineno not in candidate_linenos:
            raise GenerateDecoratorError(
                f"Could not undecorate invalid code at: submodule_path={submodule_path}, lineno={lineno}"
            )

    package_file_manager = PackageFileManager(repository, submodule_path)
    package_file_manager.remove_decorators(decorator_type, linenos)
    package_file_manager.write_to_file()


def add_reporter(
    repository: str,
    reporter_filepath: Optional[str] = None,
    force: bool = False,
) -> None:
    if REPORTER_FILE_TEMPLATE is None:
        raise GenerateReporterError("Could not load reporter template file")

    config_file = default_config_file(repository)
    configuration = load_config(config_file)

    if reporter_filepath is None:
        if configuration.reporter_filepath is not None:
            reporter_filepath = configuration.reporter_filepath
        else:
            reporter_filepath = DEFAULT_REPORTER_FILENAME
    else:
        if (
            configuration.reporter_filepath is not None
            and configuration.reporter_filepath != reporter_filepath
        ):
            raise GenerateReporterError(
                f"Configuration expects reporter to be set up at a different file than the one specified; specified={reporter_filepath}, expected={configuration.reporter_filepath}"
            )

    # Reporter filepaths must not be stored relative to the repository. They should contain the
    # repository path as a prefix.
    # If the repository is not a prefix, we prepend the repository path to the reporter_filepath to
    # make it so.
    # TODO(zomglings): This could cause errors in the future, and we should clean this up.
    if os.path.commonprefix([repository, reporter_filepath]) != repository:
        reporter_filepath = os.path.join(repository, reporter_filepath)

    if (not force) and os.path.exists(reporter_filepath):
        raise GenerateReporterError(
            f"Object already exists at desired reporter filepath: {reporter_filepath}"
        )

    if configuration.reporter_token is None:
        raise GenerateReporterError("No reporter token was specified in configuration")

    contents = REPORTER_FILE_TEMPLATE.format(
        project_name=configuration.project_name,
        reporter_object_name=configuration.reporter_object_name,
        reporter_token=configuration.reporter_token,
    )
    with open(reporter_filepath, "w") as ofp:
        ofp.write(contents)

    configuration.reporter_filepath = reporter_filepath
    save_config(config_file, configuration)
