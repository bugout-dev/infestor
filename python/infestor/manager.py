from typing import Tuple, List, Optional
import os
import libcst as cst
import logging
from . import visitors
from . import transformers

from .config import (
    default_config_file,
    load_config,
    save_config,
    python_root_relative_to_repository_root,
)

DEFAULT_REPORTER_FILENAME = "report.py"
REPORTER_FILE_TEMPLATE: Optional[str] = None
TEMPLATE_FILEPATH = os.path.join(os.path.dirname(__file__), "report.py.template")

try:
    with open(TEMPLATE_FILEPATH, "r") as ifp:
        REPORTER_FILE_TEMPLATE = ifp.read()
except Exception as e:
    logging.warn(f"WARNING: Could not load reporter template from {TEMPLATE_FILEPATH}:")
    logging.warn(e)

# TODO(zomglings): Use an Enum here.
CALL_TYPE_SYSTEM_REPORT = "system_report"
CALL_TYPE_SETUP_EXCEPTHOOK = "setup_excepthook"

DECORATOR_TYPE_RECORD_CALL = "record_call"
DECORATOR_TYPE_RECORD_ERRORS = "record_errors"


class GenerateReporterError(Exception):
    pass


class GenerateConfigurationError(Exception):
    pass


def get_reporter_module_path(
    repository: str, submodule_path: str
) -> Tuple[str, bool]:

    config_file = default_config_file(repository)
    configuration = load_config(config_file)
    if configuration is None:
        raise GenerateReporterError(
            f"Could not load configuration from file ({config_file})"
        )

    if configuration.reporter_filepath is None:
        raise GenerateReporterError(
            f"No reporter defined for project. Try running:\n\t$ infestor -r {repository} generate setup -o report.py"
        )
    reporter_filepath = os.path.join(repository, configuration.reporter_filepath)

    if not os.path.exists(submodule_path):
        raise GenerateReporterError(f"No file at submodule_path: {submodule_path}")

    path_to_reporter_file = os.path.relpath(
        os.path.join(repository, reporter_filepath),
        os.path.dirname(submodule_path),
    )
    path_components: List[str] = []
    current_path = path_to_reporter_file
    while current_path:
        current_path, base = os.path.split(current_path)
        if base == os.path.basename(reporter_filepath):
            base, _ = os.path.splitext(base)
        path_components = [base] + path_components

    name: Optional[str] = None
    if not configuration.relative_imports:
        path_components = [os.path.basename(repository)] + path_components
        name = ".".join(path_components)

    else:
        name = "." + ".".join(path_components)

    return (name, configuration.relative_imports)


class PackageFileManager:

    def __init__(self, repository: str, filepath: str):
        self.filepath = filepath
        self.repository = repository
        self._load_file(filepath)

    def _load_file(self, filepath: str):
        self.reporter_module_path, self.relative_imports = get_reporter_module_path(
            self.repository, filepath
        )
        with open(filepath, "r") as ifp:
            file_source = ifp.read()
        self._visit(cst.parse_module(file_source))

    def _visit(self, module: cst.Module):
        self.syntax_tree = cst.metadata.MetadataWrapper(module)
        self.visitor = visitors.PackageFileVisitor(self.reporter_module_path, self.relative_imports)
        self.syntax_tree.visit(self.visitor)

    def get_code(self):
        return self.syntax_tree.module.code

    def write_to_file(self):
        with open(self.filepath, "w") as ofp:
            ofp.write(self.get_code())

    def is_reporter_imported(self) -> bool:
        return self.visitor.ReporterImportedAt != -1 and self.visitor.ReporterImportedAs != ""

    def ensure_reporter_imported(self) -> bool:
        if not self.is_reporter_imported():
            raise Exception("reporter not imported")
        return True

    def get_reporter_import_lineno(self) -> int:
        self.ensure_reporter_imported()
        return self.visitor.ReporterImportedAt

    def get_reporter_import_asname(self) -> str:
        self.ensure_reporter_imported()
        return self.visitor.ReporterImportedAs

    def add_reporter_import(self) -> None:
        if self.is_reporter_imported():
            return
        transformer = transformers.ImportReporterTransformer(self.reporter_module_path)
        modified_tree = self.syntax_tree.visit(transformer)
        self._visit(modified_tree)

    def get_calls(self, call_type):
        return self.visitor.calls.get(call_type, [])

    def add_call(self, call_type):
        if self.get_calls(call_type):
            return
        transformer = transformers.ReporterCallsAdderTransformer(
            self.visitor.ReporterImportedAs,
            call_type
        )
        modified_tree = self.syntax_tree.visit(transformer)
        self._visit(modified_tree)

    def remove_call(self, call_type: str):
        transformer = transformers.ReporterCallsRemoverTransformer(
            self.visitor.ReporterImportedAs,
            call_type
        )

        modified_tree = self.syntax_tree.visit(transformer)
        self._visit(modified_tree)

    def list_decorators(self, decorator_type: str):
        return self.visitor.decorators.get(decorator_type, [])

    def decorator_candidates(self, decorator_type: str):
        decorator_candidates_visitor = visitors.DecoratorCandidatesVisitor(
            self.visitor.ReporterImportedAs,
            decorator_type
        )
        self.syntax_tree.visit(decorator_candidates_visitor)
        return decorator_candidates_visitor.decorator_candidates

    def add_decorators(self, decorator_type: str, linenos: List[int]):
        transformer = transformers.DecoratorsAdderTransformer(
            self.visitor.ReporterImportedAs,
            decorator_type,
            linenos
        )
        modified_tree = self.syntax_tree.visit(transformer)
        self._visit(modified_tree)

    def remove_decorators(self, decorator_type: str, linenos: List[int]):
        transformer = transformers.DecoratorsRemoverTransformer(
            self.visitor.ReporterImportedAs,
            decorator_type,
            linenos
        )
        modified_tree = self.syntax_tree.visit(transformer)
        self._visit(modified_tree)


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

    reporter_filepath_full = os.path.join(repository, reporter_filepath)
    if (not force) and os.path.exists(reporter_filepath_full):
        raise GenerateReporterError(
            f"Object already exists at desired reporter filepath: {reporter_filepath_full}"
        )

    if configuration.reporter_token is None:
        raise GenerateReporterError("No reporter token was specified in configuration")

    contents = REPORTER_FILE_TEMPLATE.format(
        project_name=configuration.project_name,
        reporter_token=configuration.reporter_token,
    )
    with open(reporter_filepath_full, "w") as ofp:
        ofp.write(contents)

    configuration.reporter_filepath = reporter_filepath
    save_config(config_file, configuration)