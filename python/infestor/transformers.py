import os
import pathlib
from typing import Optional, List

import libcst as cst
import libcst.matchers as m

from . import config

# TODO(yhtiyar): this is not working properly
def matches_import(node: cst.CSTNode) -> bool:
    return m.matches(
        node,
        m.SimpleStatementLine(
            body=m.MatchIfTrue(
                lambda body: all(m.matches(el, m.Import | m.ImportFrom) for el in body)
            )
        ),
    )


class ImportReporterTransformer(cst.CSTTransformer):
    """
    Imports reporter from reporter_module_path path after last naked import
    """
    def __init__(self, reporter_module_path):
        self.reporter_import_code = f"from {reporter_module_path} import reporter"
        self.last_import = None

    def visit_Module(self, node: cst.Module) -> Optional[bool]:
        for statement in node.body:
            if matches_import(statement):
                self.last_import = statement
        return False

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        new_body = []

        parsed_reporter_import = cst.parse_statement(
                    self.reporter_import_code,
                    original_node.config_for_parsing
        )

        if self.last_import is None:
            new_body.append(parsed_reporter_import)

        for el in original_node.body:
            new_body.append(el)
            if el == self.last_import:
                new_body.append(parsed_reporter_import)

        return updated_node.with_changes(
            body=new_body
        )


class ReporterCallsAdderTransformer(cst.CSTTransformer):
    def __init__(self, reporter_imported_as: str, call_type: str):
        # self.call_to_add = cst.parse_statement(f"{reporter_imported_as}.{call_type}()")
        self.call_to_add = cst.SimpleStatementLine(
            body=[
                cst.Expr(
                    value=cst.Call(
                        func=cst.Attribute(
                            value=cst.Name(
                                value=reporter_imported_as
                            ),
                            attr=cst.Name(
                                value=call_type
                            ),
                        )
                    )
                )
            ]
        )
        self.last_import = None

    def visit_Module(self, node: cst.Module) -> Optional[bool]:
        for statement in node.body:
            if matches_import(statement):
                self.last_import = statement
        return False

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        new_body = []

        if self.last_import is None:
            raise Exception("No import found when tried to add call")

        for el in original_node.body:
            new_body.append(el)
            if el == self.last_import:
                new_body.append(self.call_to_add)

        return updated_node.with_changes(
            body=new_body
        )


class ReporterCallsRemoverTransformer(cst.CSTTransformer):
    def matches_reporter_call(self, node: cst.CSTNode):
        return m.matches(
            node,
            m.SimpleStatementLine(
                body=[m.Expr(
                    value=m.Call(
                        func=m.Attribute(
                            value=m.Name(
                                value=self.reporter_imported_as
                            ),
                            attr=m.Name(
                                value=self.call_type
                            )
                        ),
                    ),
                )]
            )

        )

    def __init__(
            self,
            reporter_imported_as: str,
            call_type: str
    ):

        self.reporter_imported_as = reporter_imported_as
        self.call_type = call_type

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        new_body = []

        for el in original_node.body:
            if not self.matches_reporter_call(el):
                new_body.append(el)

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


def matches_with_reporter_decorator(node: cst.Decorator, reporter_imported_as, decorator_type):
    return m.matches(
        node,
        m.Decorator(
            decorator=m.Attribute(
                value=m.Name(
                    value=reporter_imported_as
                ),
                attr=m.Name(
                    value=decorator_type
                )
            )

        )
    )


class DecoratorsAdderTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(
            self,
            reporter_imported_as,
            decorator_type,
            lines_to_add: List[int]
    ):
        self.reporter_imported_as = reporter_imported_as
        self.lines_to_add = lines_to_add
        self.decorator_type = decorator_type
        self.decorator_to_add = cst.Decorator(
            decorator=cst.Attribute(
                value=cst.Name(
                    value=reporter_imported_as,
                ),
                attr=cst.Name(
                    value=decorator_type,
                ),
            )
        )

    def leave_FunctionDef(self, original_node, updated_node):
        position = self.get_metadata(cst.metadata.PositionProvider, original_node)
        if position.start.line not in self.lines_to_add:
            return updated_node

        decorators = [self.decorator_to_add]
        for decorator in updated_node.decorators:
            decorators.append(decorator)
            if matches_with_reporter_decorator(decorator, self.reporter_imported_as, self.decorator_type):
                return updated_node

        return updated_node.with_changes(
            decorators=decorators
        )


class DecoratorsRemoverTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(
            self,
            reporter_imported_as,
            decorator_type,
            lines_to_remove: List[int]
    ):
        self.reporter_imported_as = reporter_imported_as
        self.decorator_type = decorator_type
        self.lines_to_remove = lines_to_remove

    def leave_FunctionDef(self, original_node, updated_node):
        position = self.get_metadata(cst.metadata.PositionProvider, original_node)

        if position.start.line not in self.lines_to_remove:
            return updated_node

        decorators = []
        for decorator in updated_node.decorators:
            if not matches_with_reporter_decorator(decorator, self.reporter_imported_as, self.decorator_type):
                decorators.append(decorator)

        return updated_node.with_changes(
            decorators=decorators
        )

