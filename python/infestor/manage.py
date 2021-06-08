import ast
import importlib.util
import logging
import os
from typing import Any, cast, Dict, List, Optional, Tuple, Sequence

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


def python_files(repository: str, python_root: str) -> Sequence[str]:
    results: List[str] = []
    root = os.path.join(repository, python_root)
    if os.path.isfile(root):
        return [root]

    for dirpath, _, filenames in os.walk(root, topdown=True):
        results.extend(
            [
                os.path.join(dirpath, filename)
                for filename in filenames
                if filename.endswith(".py")
            ]
        )

    return results


def last_naked_import_ending_line_number(module: ast.Module) -> Optional[int]:
    """
    Returns the number of the line on which the last top-level import (or import from) ends.
    """
    ending_line_number = None
    for statement in module.body:
        if isinstance(statement, ast.Import) or isinstance(statement, ast.ImportFrom):
            ending_line_number = statement.end_lineno
    return ending_line_number


class CheckReporterImportedVisitor(ast.NodeVisitor):
    def __init__(self, reporter_module_path: str, relative_imports: bool):
        """
        reporter_module_path - This is the Python module path (e.g. a.b.c) to the module in which the
        reporter is defined

        This static analyzer just checks if the reporter module is imported (either as an absolute or
        relative import) in a given ast.Module object.
        """
        self.relative_imports = relative_imports
        self.reporter_module_path = reporter_module_path
        self.reporter_nakedly_imported = False
        self.reporter_imported_as: Optional[str] = None

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        if self.relative_imports:
            expected_level = 0
            for character in self.reporter_module_path:
                if character == ".":
                    expected_level += 1
                else:
                    break

            if (
                node.level == expected_level
                and node.module == self.reporter_module_path[expected_level:]
            ):
                for alias in node.names:
                    if alias.name == "reporter":
                        self.reporter_nakedly_imported = True
                        self.reporter_imported_as = "reporter"
                        if alias.asname is not None:
                            self.reporter_imported_as = alias.asname
        elif node.module == self.reporter_module_path:
            for alias in node.names:
                if alias.name == "reporter":
                    self.reporter_nakedly_imported = True
                    self.reporter_imported_as = "reporter"
                    if alias.asname is not None:
                        self.reporter_imported_as = alias.asname


def is_reporter_nakedly_imported(
    module: ast.Module, reporter_module_path: str, relative_imports: bool
) -> Tuple[bool, Optional[str]]:
    """
    Checks if a Humbug reporter has been imported at the top level of the given module (represented by its AST).

    Return a pair of the form:
    (
        <boolean value representing whether or not the module contains a reporter import>,
        <what the reporter was imported as>
    )
    """
    visitor = CheckReporterImportedVisitor(reporter_module_path, relative_imports)
    visitor.visit(module)
    return (visitor.reporter_nakedly_imported, visitor.reporter_imported_as)


def ensure_reporter_nakedly_imported(
    repository: str, python_root: str, submodule_path: str
) -> Tuple[str, Optional[int]]:
    """
    Ensures that the given submodule of Python root has imported the Humbug reporter for the Python root.

    If this method adds an import, it adds it as the last naked import in the submodule.

    Returns a pair:
    (
        <name under which the reporter has been imported in the submodule>,
        <ending line number of final naked import>
    )
    """
    config_file = default_config_file(repository)
    configuration = load_config(config_file).get(python_root)
    if configuration is None:
        raise GenerateReporterError(
            f"Could not find Python root ({python_root}) in configuration file ({config_file})"
        )

    if configuration.reporter_filepath is None:
        raise GenerateReporterError(
            f"No reporter defined for project. Try running:\n\t$ infestor -r {repository} generate setup -P {python_root} -o report.py"
        )
    reporter_filepath = os.path.join(
        repository, python_root, configuration.reporter_filepath
    )

    if not os.path.exists(submodule_path):
        raise GenerateReporterError(f"No file at submodule_path: {submodule_path}")

    module: Optional[ast.Module] = None
    with open(submodule_path, "r") as ifp:
        module = ast.parse(ifp.read())

    final_import_end_lineno = last_naked_import_ending_line_number(module)

    path_to_reporter_file = os.path.relpath(
        os.path.join(repository, python_root, reporter_filepath),
        os.path.dirname(submodule_path),
    )
    path_components: List[str] = []
    current_path = path_to_reporter_file
    while current_path:
        current_path, base = os.path.split(current_path)
        if base == os.path.basename(reporter_filepath):
            base, _ = os.path.splitext(base)
        path_components = [base] + path_components

    source_lines: List[str] = []
    with open(submodule_path, "r") as ifp:
        for line in ifp:
            source_lines.append(line)

    new_code = ""
    name: Optional[str] = None
    if not configuration.relative_imports:
        path_components = [os.path.basename(python_root)] + path_components
        name = ".".join(path_components)
        new_code = f"from {name} import reporter\n"
    else:
        name = "." + ".".join(path_components)
        new_code = f"from {name} import reporter\n"

    reporter_imported, reporter_imported_as = is_reporter_nakedly_imported(
        module, name, configuration.relative_imports
    )
    if reporter_imported:
        return (cast(str, reporter_imported_as), final_import_end_lineno)

    if final_import_end_lineno is not None:
        source_lines = (
            source_lines[:final_import_end_lineno]
            + [new_code]
            + source_lines[final_import_end_lineno:]
        )
        final_import_end_lineno += 1
    else:
        source_lines.append(new_code)
        final_import_end_lineno = len(source_lines)

    with open(submodule_path, "w") as ofp:
        for line in source_lines:
            ofp.write(line)

    # TODO(zomglings): Even the name under which reporter is imported should be parametrized!!
    return ("reporter", final_import_end_lineno)


def list_reporter_imports(
    repository: str, python_root: str, candidate_files: Optional[Sequence[str]] = None
) -> Dict[str, ast.Module]:
    """
    Args:
    1. repository - Path to repository in which Infestor has been set up
    2. python_root - Path (relative to repository) of Python package to work with (used to parse config)
    3. candidate_files - Optional list of files to restrict analysis to
    """
    results: Dict[str, ast.Module] = {}

    config_file = default_config_file(repository)
    configuration = load_config(config_file).get(python_root)
    if configuration is None:
        raise GenerateReporterError(
            f"Could not find Python root ({python_root}) in configuration file ({config_file})"
        )

    if configuration.reporter_filepath is None:
        # No infestor-managed reporter file, so just return quietly
        return results

    # Until the end of the loop, this is reversed
    reporter_filepath = os.path.join(python_root, configuration.reporter_filepath)
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
        candidate_files = python_files(repository, python_root)

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
                    module_name, python_root
                )
                if qualified_module_name == reporter_module:
                    results[candidate_file] = module

    return results


def list_calls(
    call_type: str,
    repository: str,
    python_root: str,
    candidate_files: Optional[Sequence[str]] = None,
) -> Dict[str, List[ast.Call]]:
    """
    Args:
    0. call_type - Type of call to list in the given package (e.g. "system_report", "setup_excepthook", etc.)
    1. repository - Path to repository in which Infestor has been set up
    2. python_root - Path (relative to repository) of Python package to work with (used to parse config)
    3. candidate_files - Optional list of files to restrict analysis to
    """
    results: Dict[str, List[ast.Call]] = {}
    files_with_reporter = list_reporter_imports(
        repository, python_root, candidate_files
    )

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
    python_root: str,
    submodule_path: Optional[str] = None,
) -> None:
    """
    Args:
    0. call_type - Type of call to add to the given package (e.g. "system_report", "setup_excepthook", etc.)
    1. repository - Path to repository in which Infestor has been set up
    2. python_root - Path (relative to repository) of Python package to work with (used to parse config)
    3. submodule_path: Path (relative to python_root) of file in which we want to add a sytem_report
    """
    target_file = submodule_path
    if target_file is None:
        target_file = os.path.join(repository, python_root)
        if os.path.isdir(target_file):
            target_file = os.path.join(target_file, "__init__.py")

    if not os.path.exists(target_file):
        with open(target_file, "w") as ofp:
            ofp.write("")

    existing_calls = list_calls(
        call_type, repository, python_root, candidate_files=[target_file]
    )
    if existing_calls:
        return

    reporter_imported_as, final_import_end_lineno = ensure_reporter_nakedly_imported(
        repository, python_root, target_file
    )

    source_lines: List[str] = []
    with open(target_file, "r") as ifp:
        for line in ifp:
            source_lines.append(line)

    new_code = f"{reporter_imported_as}.{call_type}()\n"
    source_lines = (
        source_lines[:final_import_end_lineno]
        + [new_code]
        + source_lines[final_import_end_lineno:]
    )

    with open(target_file, "w") as ofp:
        for line in source_lines:
            ofp.write(line)


def remove_calls(
    call_type: str,
    repository: str,
    python_root: str,
    submodule_path: Optional[str] = None,
) -> None:
    """
    Args:
    0. call_type - Type of call to remove from the given package (e.g. "system_report", "setup_excepthook", etc.)
    1. repository - Path to repository in which Infestor has been set up
    2. python_root - Path (relative to repository) of Python package to work with (used to parse config)
    3. submodule_path: Path (relative to python_root) of file in which we want to add a sytem_report
    """
    candidate_files: Sequence[Optional[str]] = [submodule_path]
    if submodule_path is None:
        candidate_files = python_files(repository, python_root)
    candidate_files = cast(Sequence[str], candidate_files)

    system_report_calls = list_calls(
        call_type, repository, python_root, candidate_files
    )

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
    python_root: str,
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
        files_to_check = list_reporter_imports(repository, python_root, candidate_files)
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
    python_root: str,
    submodule_path: str,
) -> List[ast.FunctionDef]:
    """
    Args:
    0. decorator_type - Type of decorator to add to the given package (choices: "record_call", "record_error")
    1. repository - Path to repository in which Infestor has been set up
    2. python_root - Path (relative to repository) of Python package to work with (used to parse config)
    3. submodule_path: Path (relative to python_root) of file in which we want to add a sytem_report

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
        python_root,
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
    python_root: str,
    submodule_path: str,
    linenos: List[int],
) -> None:
    """
    Args:
    0. decorator_type - Type of decorator to add to the given package (choices: "record_call", "record_error")
    1. repository - Path to repository in which Infestor has been set up
    2. python_root - Path (relative to repository) of Python package to work with (used to parse config)
    3. submodule_path: Path (relative to python_root) of file in which we want to add a sytem_report
    4. linenos: Line numbers where functions are defined that we wish to decorate
    """
    candidate_function_definitions = decorator_candidates(
        decorator_type, repository, python_root, submodule_path
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
        repository, python_root, submodule_path
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
    python_root: str,
    submodule_path: str,
    linenos: List[int],
) -> None:
    """
    Args:
    0. decorator_type - Type of decorator to remove from the given package (choices: "record_call", "record_error")
    1. repository - Path to repository in which Infestor has been set up
    2. python_root - Path (relative to repository) of Python package to work with (used to parse config)
    3. submodule_path: Path (relative to python_root) of file in which we want to add a sytem_report
    4. linenos: Line numbers where decorated functions are defined that we wish to undecorate
    """
    wrapped_function_definitions = list_decorators(
        decorator_type, repository, python_root, [submodule_path]
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
    python_root: str,
    reporter_filepath: Optional[str] = None,
    force: bool = False,
) -> None:
    if REPORTER_FILE_TEMPLATE is None:
        raise GenerateReporterError("Could not load reporter template file")

    config_file = default_config_file(repository)
    configurations_by_python_root = load_config(config_file)
    normalized_python_root = python_root_relative_to_repository_root(
        repository, python_root
    )

    configuration = configurations_by_python_root.get(normalized_python_root)
    if configuration is None:
        raise GenerateReporterError(
            f"Could not find configuration for python root ({python_root}) in config file ({config_file})"
        )

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

    reporter_filepath_full = os.path.join(
        repository, configuration.python_root, reporter_filepath
    )
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
