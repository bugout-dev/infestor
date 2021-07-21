from typing import Tuple, List, Optional
import os
from pathlib import Path

import libcst as cst

from . import visitors
from . import transformers
from .errors import *
from .config import (
    default_config_file,
    load_config,
    InfestorConfiguration,
)

# TODO(zomglings): Use an Enum here.
CALL_TYPE_SYSTEM_REPORT = "system_report"
CALL_TYPE_SETUP_EXCEPTHOOK = "setup_excepthook"

DECORATOR_TYPE_RECORD_CALL = "record_call"
DECORATOR_TYPE_RECORD_ERRORS = "record_errors"


def get_reporter_import_information(
    repository: str,
    submodule_path: str,
    configuration: Optional[InfestorConfiguration] = None,
) -> Tuple[str, bool, str]:
    """
    Reads reporter import information (for the given submodule) from the config file for the given repository.

    Returns: A tuple containing 3 values:
    1. reporter_module_path - this is the import path from the submodule at the given submodule_path
       for the module containing the repoter.
    2. is_import_relative - True or False depending on whether the reporter module path represents
       an import relative to the repository package or not
    3. reporter_variable_name - The name of the variable representing the HumbugReporter in the
       reporter module for the given repository.
    """
    if configuration is None:
        config_file = default_config_file(repository)
        configuration = load_config(config_file)
        if configuration is None:
            raise GenerateReporterError(
                f"Could not load configuration from file ({config_file})"
            )

    if configuration.reporter_filepath is None:
        raise GenerateReporterError(f"No reporter defined for project.")

    # We will set this in the next if-else statement.
    import_path = ""

    if configuration.relative_imports:
        # TODO(zomglings): Check that common_ancestor is a subpath of repository. Raise error if it is not.
        common_ancestor = os.path.commonpath(
            [submodule_path, configuration.reporter_filepath]
        )
        common_ancestor_to_submodule_path = Path(
            os.path.relpath(submodule_path, start=common_ancestor)
        )
        common_ancestor_to_reporter_relpath = Path(
            os.path.relpath(configuration.reporter_filepath, start=common_ancestor)
        )

        num_dots = len(common_ancestor_to_submodule_path.parts) - 1
        import_dots = "." * num_dots

        common_ancestor_to_reporter_path_components = list(
            common_ancestor_to_reporter_relpath.parts[:-1]
        )
        reporter_filename = common_ancestor_to_reporter_relpath.parts[-1]
        reporter_basename, _ = os.path.splitext(reporter_filename)
        common_ancestor_to_reporter_path_components.append(reporter_basename)

        import_path = (
            f"{import_dots}.{'.'.join(common_ancestor_to_reporter_path_components)}"
        )
    else:
        repository_to_reporter_path = Path(
            os.path.relpath(configuration.reporter_filepath, start=repository)
        )
        repository_to_reporter_path_components = list(
            repository_to_reporter_path.parts[:-1]
        )
        reporter_filename = repository_to_reporter_path.parts[-1]
        reporter_basename, _ = os.path.splitext(reporter_filename)
        repository_to_reporter_path_components.append(reporter_basename)

        repository_name = os.path.basename(repository)

        import_path = (
            f"{repository_name}.{'.'.join(repository_to_reporter_path_components)}"
        )

    return (
        import_path,
        configuration.relative_imports,
        configuration.reporter_object_name,
    )


class PackageFileManager:
    def __init__(self, repository: str, filepath: str):
        self.filepath = filepath
        self.repository = repository
        self._load_file(filepath)

    def _load_file(self, filepath: str):
        (
            self.reporter_module_path,
            self.relative_imports,
            self.reporter_object_name,
        ) = get_reporter_import_information(self.repository, filepath)
        with open(filepath, "r") as ifp:
            file_source = ifp.read()
        self._visit(cst.parse_module(file_source))

    def _visit(self, module: cst.Module):
        self.syntax_tree = cst.metadata.MetadataWrapper(module)
        self.visitor = visitors.PackageFileVisitor(
            self.reporter_module_path, self.relative_imports, self.reporter_object_name
        )
        self.syntax_tree.visit(self.visitor)

    def get_code(self):
        return self.syntax_tree.module.code

    def write_to_file(self):
        with open(self.filepath, "w") as ofp:
            ofp.write(self.get_code())

    def is_reporter_imported(self) -> bool:
        return (
            self.visitor.ReporterImportedAt != -1
            and self.visitor.ReporterImportedAs != ""
        )

    def ensure_import_reporter(self):
        if not self.is_reporter_imported():
            self.add_reporter_import()

    def add_reporter_import(self) -> None:
        if self.is_reporter_imported():
            return
        transformer = transformers.ImportReporterTransformer(
            self.reporter_module_path, self.reporter_object_name
        )
        modified_tree = self.syntax_tree.visit(transformer)
        self._visit(modified_tree)

        if (
            self.visitor.ReporterImportedAs == ""
            or self.visitor.ReporterImportedAt == -1
        ):
            raise GenerateReporterError(
                f"Failed to import reporter \n{self.get_code()}"
            )

    def get_calls(self, call_type):
        return self.visitor.calls.get(call_type, [])

    def add_call(self, call_type):
        if self.get_calls(call_type):
            return
        self.ensure_import_reporter()
        transformer = transformers.ReporterCallsAdderTransformer(
            self.visitor.ReporterImportedAs, call_type
        )
        modified_tree = self.syntax_tree.visit(transformer)
        self._visit(modified_tree)

    def remove_call(self, call_type: str):
        transformer = transformers.ReporterCallsRemoverTransformer(
            self.visitor.ReporterImportedAs, call_type
        )

        modified_tree = self.syntax_tree.visit(transformer)
        self._visit(modified_tree)

    def list_decorators(self, decorator_type: str):
        return self.visitor.decorators.get(decorator_type, [])

    def decorator_candidates(self, decorator_type: str):
        decorator_candidates_visitor = visitors.DecoratorCandidatesVisitor(
            self.visitor.ReporterImportedAs, decorator_type
        )
        self.syntax_tree.visit(decorator_candidates_visitor)
        return decorator_candidates_visitor.decorator_candidates

    def add_decorators(self, decorator_type: str, linenos: List[int]):
        func_linenos = linenos
        if not self.is_reporter_imported():
            # Reporter not importer, we need to add reporter
            self.add_reporter_import()
            # Since we added reporter, source has changed and
            # all linenos need to be increased by 1
            func_linenos = [x + 1 for x in func_linenos]

        transformer = transformers.DecoratorsAdderTransformer(
            self.visitor.ReporterImportedAs, decorator_type, func_linenos
        )
        modified_tree = self.syntax_tree.visit(transformer)
        self._visit(modified_tree)
        if decorator_type == DECORATOR_TYPE_RECORD_ERRORS:
            # We've added decorator which shifts linenos
            try_except_transformer = transformers.TryExceptAdderTransformer(
                self.visitor.ReporterImportedAs, [x + 1 for x in func_linenos]
            )
            modified_tree = self.syntax_tree.visit(try_except_transformer)
            self._visit(modified_tree)

    def remove_decorators(self, decorator_type: str, linenos: List[int]):
        transformer = transformers.DecoratorsRemoverTransformer(
            self.visitor.ReporterImportedAs, decorator_type, linenos
        )
        modified_tree = self.syntax_tree.visit(transformer)
        self._visit(modified_tree)

        if decorator_type == DECORATOR_TYPE_RECORD_ERRORS:
            try_except_transformer = transformers.TryExceptRemoverTransformer(
                self.visitor.ReporterImportedAs, [x - 1 for x in linenos]
            )
            modified_tree = self.syntax_tree.visit(try_except_transformer)
            self._visit(modified_tree)
