import pathlib
from typing import Optional, List

import libcst as cst
import libcst.matchers as m

from . import config

def matches_import(node: cst.CSTNode) -> bool:
    return m.matches(
        node,
        m.SimpleStatementLine(
            body=[m.Import | m.ImportFrom]
        )
    )

class ImportReporterError(Exception):
    """
    This error is raised when the ImportReporterTransformer fails to ensure that a reporter is
    imported in a module.
    """
    pass

class ImportReporterTransformer(cst.CSTTransformer):
    """
    Makes sure that reporter is imported in a module so that any downstream code generation (which
    depends on this import) functions correctly.
    """
    def __init__(self, repository: str):
        self._repository = repository
        self._config_file = config.default_config_file(repository)
        self._config = config.load_config(self._config_file)

        self.reporter_import: Optional[cst.CSTNode] = None

    def import_name(self):
        if self._config.reporter_filepath is None:
            raise ImportReporterError(f"No reporter available in package: {self._repository}")

        reporter_filepath = pathlib.Path(self._config.reporter_filepath)
        if not reporter_filepath.is_file():
            raise ImportReporterError(f"Reporter path does not contain a file: {self._config.reporter_filepath}")

        components: List[str] = []

class NakedTransformer(cst.CSTTransformer):
    """
    Adds given imports and calls sources after last naked import.
    First it adds imports, then calls
    It is was supposed for temporary use to test out libcst
    """
    last_import = None

    def __init__(
            self,
            imports_to_add: Optional[List[str]],  # list of sources,
            calls_to_add: Optional[List[str]],  # list of sources
    ):

        self.imports_to_add = imports_to_add
        if self.imports_to_add is None:
            self.imports_to_add = []
        self.calls_to_add = calls_to_add
        if self.calls_to_add is None:
            self.calls_to_add = []

    def visit_Module(self, node: cst.Module) -> Optional[bool]:
        for statement in node.body:
            if matches_import(statement):
                self.last_import = statement
        return False

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        new_body = []

        def add_sources():
            for import_code in self.imports_to_add:
                new_body.append(cst.parse_statement(
                    import_code,
                    original_node.config_for_parsing)
                )
            for call_code in self.calls_to_add:
                new_body.append(cst.parse_statement(
                    call_code,
                    original_node.config_for_parsing)
                )

        for el in original_node.body:
            new_body.append(el)
            if el == self.last_import:
                add_sources()
        if self.last_import is None:
            add_sources()

        return updated_node.with_changes(
            body=new_body
        )


ERROR_REPORT_CODE = "error_report"


class TryCatchTransformer(cst.CSTTransformer):
    def __init__(self, reported_imported_as: str):
        self.reporter_imported_as = reported_imported_as

    def has_except_asname(self, node: cst.ExceptHandler):
        return m.matches(
            node,
            m.ExceptHandler(
                name=m.AsName(
                    name=m.Name()
                )
            )
        )

    def matches_error_report_call(self, node: cst.Call, except_as_name):
        return m.matches(
            node,
            m.Call(
                func=m.Attribute(
                    value=m.Name(
                        value=self.reporter_imported_as
                    ),
                    attr=m.Name(
                        value="error_report"
                    ),
                ),
                args=[m.Arg(
                    value=m.Name(
                        value=except_as_name
                    )
                )]
            ),
        )

    def matches_error_report_statement(self, node: cst.SimpleStatementLine, except_as_name):
        return m.matches(
            node,
            m.SimpleStatementLine(
                body=[m.Expr(
                    value=m.MatchIfTrue(
                        lambda value: self.matches_error_report_call(value, except_as_name)
                    )
                )]
            )
        )

    def leave_ExceptHandler(self, node: cst.ExceptHandler, updated_node: cst.ExceptHandler) -> cst.CSTNode:
        asname = "e"
        new_name = node.name
        except_type = node.type

        if except_type is None:
            except_type = cst.Name(value="Exception")

        if self.has_except_asname(node):
            asname = node.name.name.value
        else:
            new_name = cst.AsName(name=cst.Name(value=asname))


        new_inner_body = []
        has_called_error_report = False
        for el in updated_node.body.body:   # Using updated node, since child od node is updated
            new_inner_body.append(el)
            if (
                    isinstance(el, cst.SimpleStatementLine)
                    and self.matches_error_report_statement(el, asname)
            ):
                has_called_error_report = True

        if not has_called_error_report:
            new_inner_body.append(
                cst.parse_statement(
                    f"{self.reporter_imported_as}.{ERROR_REPORT_CODE}({asname})"
                ))
        new_body = updated_node.body.with_changes(
            body=new_inner_body
        )

        return updated_node.with_changes(
            name=new_name,
            type=except_type,
            body=new_body,
            whitespace_after_except=cst.SimpleWhitespace(
             value=' ',
            ),
        )


