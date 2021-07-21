from typing import Optional, List, Tuple, Dict, cast

import libcst.matchers as m
import libcst as cst
import logging
from . import models
from . import manager
from . import transformers


class ReporterNotImported(Exception):
    pass


class ReporterFileVisitor(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self):
        self.HumbugConsentImportedAs: str = ""
        self.HumbugConsentImportedAt: int = -1
        self.HumbugReporterImportedAs: str = ""
        self.HumbugReporterImportedAt: int = -1
        self.HumbugConsentInstantiatedAt: int = -1
        self.HumbugConsentInstantiatedAs: str = ""
        self.HumbugReporterInstantiatedAs: str = ""
        self.HumbugReporterInstantiatedAt: int = -1
        self.HumbugReporterConsentArgument: str = ""
        self.HumbugReporterTokenArgument: str = ""

    @staticmethod
    def syntax_tree(reporter_filepath: str) -> cst.MetadataWrapper:
        with open(reporter_filepath, "r") as ifp:
            reporter_file_source = ifp.read()
        reporter_syntax_tree = cst.metadata.MetadataWrapper(
            cst.parse_module(reporter_file_source)
        )
        return reporter_syntax_tree

    def visit_ImportFrom(self, node: cst.ImportFrom) -> Optional[bool]:
        position = self.get_metadata(cst.metadata.PositionProvider, node)  # type: ignore
        if (
            isinstance(node.module, cst.Attribute)
            and isinstance(node.module.value, cst.Name)
            and node.module.value.value == "humbug"
        ):
            if node.module.attr.value == "consent" and not isinstance(
                node.names, cst.ImportStar
            ):
                for name in node.names:
                    if name.name.value == "HumbugConsent":
                        self.HumbugConsentImportedAs = "HumbugConsent"

                        if name.asname is not None and isinstance(
                            name.asname, cst.Name
                        ):
                            self.HumbugConsentImportedAs = name.asname.value

                        self.HumbugConsentImportedAt = position.start.line
            elif node.module.attr.value == "report" and not isinstance(
                node.names, cst.ImportStar
            ):
                for name in node.names:
                    if name.name.value == "HumbugReporter":
                        self.HumbugReporterImportedAs = "HumbugReporter"

                        if name.asname is not None and isinstance(
                            name.asname, cst.Name
                        ):
                            self.HumbugReporterImportedAs = name.asname.value

                        self.HumbugReporterImportedAt = position.start.line

        return False

    def visit_Assign(self, node: cst.Assign) -> Optional[bool]:
        if (
            len(node.targets) == 1
            and isinstance(node.value, cst.Call)
            and isinstance(node.value.func, cst.Name)
            and isinstance(node.targets[0].target, cst.Name)
        ):
            if node.value.func.value == self.HumbugConsentImportedAs:
                position = self.get_metadata(cst.metadata.PositionProvider, node)  # type: ignore
                self.HumbugConsentInstantiatedAt = position.start.line
                self.HumbugConsentInstantiatedAs = node.targets[0].target.value
                return False
            elif node.value.func.value == self.HumbugReporterImportedAs:
                position = self.get_metadata(cst.metadata.PositionProvider, node)  # type: ignore
                self.HumbugReporterInstantiatedAt = position.start.line
                self.HumbugReporterInstantiatedAs = node.targets[0].target.value
        return True

    def visit_Call(self, node: cst.Call) -> Optional[bool]:
        if (
            isinstance(node.func, cst.Name)
            and node.func.value == self.HumbugReporterImportedAs
        ):
            for arg in node.args:
                if (
                    arg.keyword is not None
                    and arg.keyword.value == "consent"
                    and isinstance(arg.value, cst.Name)
                ):
                    self.HumbugReporterConsentArgument = arg.value.value
                elif (
                    arg.keyword is not None
                    and arg.keyword.value == "bugout_token"
                    and isinstance(arg.value, cst.SimpleString)
                ):
                    self.HumbugReporterTokenArgument = arg.value.value
        return False


class DecoratorCandidatesVisitor(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, reporter_imported_as, decorator_type):
        self.reporter_imported_as = reporter_imported_as
        self.decorator_type = decorator_type
        self.scope_stack: List[str] = []
        self.decorator_candidates: List[models.ReporterDecoratorCandidate] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> Optional[bool]:
        self.scope_stack.append(node.name.value)

        for decorator in node.decorators:
            if transformers.matches_with_reporter_decorator(
                decorator, self.reporter_imported_as, self.decorator_type
            ):
                return True

        position = self.get_metadata(cst.metadata.PositionProvider, node)
        self.decorator_candidates.append(
            models.ReporterDecoratorCandidate(
                scope_stack=".".join(self.scope_stack), lineno=position.start.line
            )
        )
        return True

    def leave_FunctionDef(self, original_node: cst.FunctionDef) -> None:
        self.scope_stack.pop()

    def visit_ClassDef(self, node: cst.ClassDef) -> Optional[bool]:
        self.scope_stack.append(node.name.value)
        return True

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        self.scope_stack.pop()


class PackageFileVisitor(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)
    last_import_lineno = 0

    def __init__(
        self,
        reporter_module_path: str,
        relative_imports: bool,
        reporter_object_name: str = "reporter",
    ):
        self.ReporterImportedAs: str = ""
        self.ReporterImportedAt: int = -1
        self.ReporterCorrectlyImported: bool = False

        self.relative_imports = relative_imports
        self.reporter_module_path = reporter_module_path
        self.scope_stack: List[str] = []
        self.reporter_object_name = reporter_object_name
        self.seeking_import_node = cst.parse_statement(
            f"from {reporter_module_path} import {reporter_object_name}"
        )

        self.calls: Dict[str, List[models.ReporterCall]] = {}
        self.decorators: Dict[str, List[models.ReporterDecorator]] = {}

    # TODO(yhtiyar) also add checking with 'import'
    def matches_with_package_import(self, node: cst.ImportFrom):
        return m.matches(
            node,
            m.ImportFrom(
                module=m.Attribute(
                    value=m.Name(
                        # TODO: Refactor this
                        value=self.reporter_module_path.rsplit(".", 1)[
                            0
                        ]  # checking for reporter module path basename
                    ),
                    attr=m.Name(value="report"),
                ),
            ),
        )

    def matches_reporter_call(self, node: cst.Call):
        return m.matches(
            node,
            m.Call(
                func=m.Attribute(
                    value=m.Name(value=self.ReporterImportedAs),
                ),
            ),
        )

    def matches_with_reporter_decorator(self, node: cst.Decorator):
        return m.matches(
            node,
            m.Decorator(
                decorator=m.Attribute(
                    value=m.Name(value=self.ReporterImportedAs),
                )
            ),
        )

    def visit_FunctionDef(self, node: cst.FunctionDef):
        self.scope_stack.append(node.name.value)
        for decorator in node.decorators:
            if self.matches_with_reporter_decorator(decorator):
                position = self.get_metadata(cst.metadata.PositionProvider, node)
                decorator_attribute = cast(cst.Attribute, decorator.decorator)
                decorator_model = models.ReporterDecorator(
                    decorator_type=decorator_attribute.attr.value,
                    scope_stack=".".join(self.scope_stack),
                    lineno=position.start.line,
                )
                self.decorators.setdefault(decorator_model.decorator_type, []).append(
                    decorator_model
                )
        return True

    def leave_FunctionDef(self, original_node: cst.FunctionDef) -> None:
        self.scope_stack.pop()

    def visit_ClassDef(self, node: cst.ClassDef):
        self.scope_stack.append(node.name.value)
        return True

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        self.scope_stack.pop()

    def visit_Import(self, node: cst.Import) -> Optional[bool]:
        if self.scope_stack:
            return False
        position = self.get_metadata(cst.metadata.PositionProvider, node)
        self.last_import_lineno = position.end.line
        return False

    def check_alias_for_reporter(self, import_aliases, position):
        for alias in import_aliases:
            name = alias.name.value
            if name == self.reporter_object_name:
                asname = alias.asname
                if asname:
                    self.ReporterImportedAs = asname.name.value
                else:
                    self.ReporterImportedAs = name
                self.ReporterImportedAt = position.start.line
                self.ReporterCorrectlyImported = (
                    position.start.line == self.last_import_lineno + 1
                )

    def visit_ImportFrom(self, node: cst.ImportFrom) -> Optional[bool]:
        if self.scope_stack:
            return False
        position = self.get_metadata(cst.metadata.PositionProvider, node)

        temp_node = cst.SimpleStatementLine(body=[node])
        if temp_node.deep_equals(self.seeking_import_node):
            self.ReporterImportedAs = self.reporter_object_name
            self.ReporterImportedAt = position.start.line
            self.ReporterCorrectlyImported = (
                position.start.line == self.last_import_lineno + 1
            )

        self.last_import_lineno = position.end.line
        return False

    def visit_Call(self, node: cst.Call) -> Optional[bool]:
        if self.ReporterImportedAt == -1:
            return False
        if self.matches_reporter_call(node):
            position = self.get_metadata(cst.metadata.PositionProvider, node)
            func_attr = cast(cst.Attribute, node.func)
            call_model = models.ReporterCall(
                call_type=func_attr.attr.value,
                lineno=position.start.line,
                scope_stack=".".join(self.scope_stack),
            )
            self.calls.setdefault(call_model.call_type, []).append(call_model)
        return False
