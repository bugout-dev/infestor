import ast
import importlib.util
import logging
import os
from typing import Any, cast, Dict, List, Optional, Tuple, Sequence
import libcst as cst
from . import transformers
from . import visitors
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


class GenerateDecoratorError(Exception):
    pass


class CallVisitor(ast.NodeVisitor):
    def __init__(self):
        self.calls: List[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> Any:
        self.calls.append(node)


class FunctionDefVisitor(ast.NodeVisitor):
    def __init__(self):
        self.function_definitions: List[ast.FunctionDef] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_definitions.append(node)
        self.generic_visit(node)


class PackageFileManager:

    def __init__(self, file_path: str, reporter_module_path: str, relative_imports: bool):
        self.reporter_module_path = reporter_module_path
        self.relative_imports = relative_imports
        self.file_path = file_path

        with open(file_path, "r") as ifp:
            file_source = ifp.read()
        self.__visit(cst.parse_module(file_source))

    def __visit(self, module: cst.Module):
        self.syntax_tree = cst.metadata.MetadataWrapper(module)
        self.visitor = visitors.PackageFileVisitor(self.reporter_module_path, self.relative_imports)
        self.syntax_tree.visit(self.visitor)

    def get_code(self):
        return self.syntax_tree.module.code

    def write_to_file(self):
        with open(self.file_path, "w") as ofp:
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
        self.__visit(modified_tree)

    def is_system_report_called(self) -> bool:
        return self.visitor.ReporterSystemCallAt != -1

    def get_system_report_lineno(self):
        return self.visitor.ReporterSystemCallAt

    def add_call(self, call_type):
        if self.is_system_report_called():
            return
        call_source_code = f"{self.visitor.ReporterImportedAs}.{call_type}()"
        transformer = transformers.ReporterCallsTransformer([call_source_code])
        modified_tree = self.syntax_tree.visit(transformer)
        self.__visit(modified_tree)

    def is_excepthook_called(self) -> bool:
        return self.visitor.ReporterExcepthookAt != -1


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


def ensure_reporter_nakedly_imported(
    repository: str, submodule_path: str
) -> Tuple[str, Optional[int]]:
    """
    Ensures that the given submodule has imported the Humbug reporter.

    If this method adds an import, it adds it as the last naked import in the submodule.

    Returns a pair:
    (
        <name under which the reporter has been imported in the submodule>,
        <ending line number of final naked import>
    )
    """
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

    package_file_manager = PackageFileManager(submodule_path, name, configuration.relative_imports)
    if package_file_manager.is_reporter_imported():
        return (package_file_manager.get_reporter_import_asname(),
                package_file_manager.get_reporter_import_lineno())

    package_file_manager.add_reporter_import()
    package_file_manager.write_to_file()
    print(package_file_manager.get_code())
    # TODO(zomglings): Even the name under which reporter is imported should be parametrized!!
    return ("reporter", package_file_manager.get_reporter_import_lineno())


def list_reporter_imports(
    repository: str, candidate_files: Optional[Sequence[str]] = None
) -> Dict[str, PackageFileManager]:
    """
    Args:
    1. repository - Path to repository in which Infestor has been set up
    2. candidate_files - Optional list of files to restrict analysis to
    """
    results: Dict[str, ast.Module] = {}

    config_file = default_config_file(repository)
    configuration = load_config(config_file)
    if configuration is None:
        raise GenerateReporterError(
            f"Could not load configuration from file ({config_file})"
        )

    if configuration.reporter_filepath is None:
        # No infestor-managed reporter file, so just return quietly
        return results

    # Until the end of the loop, this is reversed
    reporter_filepath = configuration.reporter_filepath
    dirname, basename = os.path.split(reporter_filepath)
    base_module, _ = os.path.splitext(basename)
    reporter_module_components: List[str] = [base_module]
    while True:
        dirname, basename = os.path.split(dirname)
        if basename == "":
            break
        reporter_module_components.append(basename)
        if dirname == "":
            break
    reporter_module_components.reverse()
    reporter_module = ".".join(reporter_module_components)

    if candidate_files is None:
        candidate_files = python_files(repository)

    for candidate_file in candidate_files:
        module: Optional[ast.Module] = None
        with open(candidate_file, "r") as ifp:
            module = ast.parse(ifp.read())

        for statement in module.body:
            if isinstance(statement, ast.Import):
                for name in statement.names:
                    if name.name == reporter_module:
                        results[candidate_file] = module
            elif isinstance(statement, ast.ImportFrom):
                module_name = f"{'.'*statement.level}{statement.module}"
                qualified_module_name = importlib.util.resolve_name(
                    module_name, repository
                )
                if qualified_module_name == reporter_module:
                    results[candidate_file] = module

    return results


def list_calls(
    call_type: str,
    repository: str,
    candidate_files: Optional[Sequence[str]] = None,
) -> Dict[str, List[ast.Call]]:
    """
    Args:
    0. call_type - Type of call to list in the given package (e.g. "system_report", "setup_excepthook", etc.)
    1. repository - Path to repository in which Infestor has been set up
    2. candidate_files - Optional list of files to restrict analysis to
    """
    results: Dict[str, List[ast.Call]] = {}
    files_with_reporter = list_reporter_imports(repository, candidate_files)

    call_logger = CallVisitor()
    for filepath, file_ast in files_with_reporter.items():
        calls: List[ast.Call] = []
        call_logger.calls = []
        call_logger.visit(file_ast)

        for call_object in call_logger.calls:
            if (
                isinstance(call_object.func, ast.Name)
                and call_object.func.id == call_type
            ):
                calls.append(call_object)
            elif (
                isinstance(call_object.func, ast.Attribute)
                and call_object.func.attr == call_type
            ):
                calls.append(call_object)

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
    #package_file_manager = PackageFileManager()
    #TODO(yhtiyar) Remove this:
    existing_calls = list_calls(call_type, repository, candidate_files=[target_file])
    if existing_calls:
        return

    reporter_imported_as, final_import_end_lineno = ensure_reporter_nakedly_imported(
        repository, target_file
    )

    #TODO (yhtiyar) Add calls




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
    candidate_files: Sequence[Optional[str]] = [submodule_path]
    if submodule_path is None:
        candidate_files = python_files(repository)
    candidate_files = cast(Sequence[str], candidate_files)

    system_report_calls = list_calls(call_type, repository, candidate_files)

    for filepath, calls in system_report_calls.items():
        deletions: List[Tuple[int, Optional[int]]] = [
            (report_call.lineno, report_call.end_lineno) for report_call in calls
        ]

        if deletions:
            current_deletion = 0
            new_lines = []
            with open(filepath, "r") as ifp:
                for j, line in enumerate(ifp):
                    i = j + 1
                    if i >= deletions[current_deletion][0] and (
                        deletions[current_deletion][1] is None
                        or i <= cast(int, deletions[current_deletion][1])
                    ):
                        if current_deletion + 1 < len(deletions):
                            current_deletion += 1
                        continue
                    else:
                        new_lines.append(line)

            with open(filepath, "w") as ofp:
                ofp.write("".join(new_lines))


def list_decorators(
    decorator_type: str,
    repository: str,
    candidate_files: Optional[Sequence[str]] = None,
    skip_reporter_check: bool = False,
    complement: bool = False,
) -> Dict[str, List[ast.FunctionDef]]:
    """
    Args:
    0. decorator_type - Type of decorator to list in the given package (choices: "record_call", "record_error")
    1. repository - Path to repository in which Infestor has been set up
    2. python_root - Path (relative to repository) of Python package to work with (used to parse config)
    3. candidate_files - Optional list of files to restrict analysis to

    Returns a dictionary mapping file paths to functions defined in those files decorated by the given decorator_type method
    on a managed Humbug reporter.
    """
    results: Dict[str, List[ast.FunctionDef]] = {}

    files_to_check: Optional[Dict[str, ast.Module]] = None
    if not skip_reporter_check:
        files_to_check = list_reporter_imports(repository, candidate_files)
    else:
        files_to_check = {}
        if candidate_files is not None:
            for candidate_file in candidate_files:
                with open(candidate_file, "r") as ifp:
                    files_to_check[candidate_file] = ast.parse(ifp.read())

    for candidate_file, module in files_to_check.items():
        admissible_function_definitions: List[ast.FunctionDef] = []
        visitor = FunctionDefVisitor()
        visitor.visit(module)
        for function_definition in visitor.function_definitions:
            decorated = False
            for decorator in function_definition.decorator_list:
                # TODO(zomglings): Make this check more comprehensive (additionally using reporter_imported_as).
                # After all, there could be another decorator with an attr value of record_call.
                if (
                    isinstance(decorator, ast.Attribute)
                    and decorator.attr == decorator_type
                ):
                    decorated = True
                    if not complement:
                        admissible_function_definitions.append(function_definition)
            if complement and not decorated:
                admissible_function_definitions.append(function_definition)
        if admissible_function_definitions:
            results[candidate_file] = admissible_function_definitions

    return results


def decorator_candidates(
    decorator_type: str,
    repository: str,
    submodule_path: str,
) -> List[ast.FunctionDef]:
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
    wrapped_undecorated_function_definitions = list_decorators(
        decorator_type,
        repository,
        [submodule_path],
        skip_reporter_check=True,
        complement=True,
    )
    undecorated_function_definitions = wrapped_undecorated_function_definitions.get(
        submodule_path, []
    )
    return undecorated_function_definitions


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
    candidate_function_definitions = decorator_candidates(
        decorator_type, repository, submodule_path
    )
    candidate_linenos = {
        function_definition.lineno
        for function_definition in candidate_function_definitions
    }
    for lineno in linenos:
        if lineno not in candidate_linenos:
            raise GenerateDecoratorError(
                f"Non-candidate source code: submodule_path={submodule_path}, lineno={lineno}"
            )

    reporter_imported_as, _ = ensure_reporter_nakedly_imported(
        repository, submodule_path
    )

    chosen_function_definitions = [
        function_definition
        for function_definition in candidate_function_definitions
        if function_definition.lineno in linenos
    ]

    chosen_function_definitions_with_boundary = [
        (
            function_definition,
            min(
                [
                    function_definition.lineno,
                    *[
                        decorator.lineno
                        for decorator in function_definition.decorator_list
                    ],
                ]
            ),
        )
        for function_definition in chosen_function_definitions
    ]
    chosen_function_definitions_with_boundary.sort(key=lambda p: p[1])

    source_lines: List[str] = []
    with open(submodule_path, "r") as ifp:
        for line in ifp:
            source_lines.append(line)

    new_source_lines: List[str] = []
    sl_index = 0
    fd_index = 0
    for source_line in source_lines:
        source_lineno = sl_index + 1
        function_definition, boundary = chosen_function_definitions_with_boundary[
            fd_index
        ]
        if source_lineno == boundary:
            new_source_lines.append(
                f"{' '*function_definition.col_offset}@{reporter_imported_as}.{decorator_type}\n"
            )
            fd_index += 1
            if fd_index >= len(chosen_function_definitions_with_boundary):
                break
        new_source_lines.append(source_line)
        sl_index += 1

    new_source_lines.extend(source_lines[sl_index:])
    with open(submodule_path, "w") as ofp:
        for line in new_source_lines:
            ofp.write(line)


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
    wrapped_function_definitions = list_decorators(
        decorator_type, repository, [submodule_path]
    )
    decorated_functions = wrapped_function_definitions.get(submodule_path, [])
    decorated_function_linenos = {
        function_definition.lineno for function_definition in decorated_functions
    }
    for lineno in linenos:
        if lineno not in decorated_function_linenos:
            raise GenerateDecoratorError(
                f"Could not undecorate invalid code at: submodule_path={submodule_path}, lineno={lineno}"
            )

    deletions: List[Tuple[int, Optional[int]]] = []
    for function_definition in decorated_functions:
        if function_definition.lineno in linenos:
            for decorator in function_definition.decorator_list:
                if (
                    isinstance(decorator, ast.Attribute)
                    and decorator.attr == decorator_type
                ):
                    deletions.append((decorator.lineno, decorator.end_lineno))

    source_lines: List[str] = []
    with open(submodule_path, "r") as ifp:
        for line in ifp:
            source_lines.append(line)

    current_deletion = 0
    sl_index = 0

    new_source_lines: List[str] = []
    capture = True

    while current_deletion < len(deletions) and sl_index < len(source_lines):
        current_deletion_start, current_deletion_end = deletions[current_deletion]
        capture = not (
            sl_index + 1 >= current_deletion_start
            and (current_deletion_end is None or sl_index + 1 <= current_deletion_end)
        )
        if capture:
            new_source_lines.append(source_lines[sl_index])

        if sl_index == current_deletion_end:
            current_deletion += 1

        sl_index += 1

    new_source_lines.extend(source_lines[sl_index:])
    with open(submodule_path, "w") as ofp:
        for line in new_source_lines:
            ofp.write(line)


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
