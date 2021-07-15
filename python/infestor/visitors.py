from typing import Optional, List, Tuple, Dict

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
    def syntax_tree(reporter_filepath: str) -> cst.Module:
        with open(reporter_filepath, "r") as ifp:
            reporter_file_source = ifp.read()
        reporter_syntax_tree = cst.metadata.MetadataWrapper(cst.parse_module(reporter_file_source))
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
                scope_stack=".".join(self.scope_stack),
                lineno=position.start.line
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

    def __init__(self, reporter_module_path: str, relative_imports: bool):
        self.ReporterImportedAs: str = ""
        self.ReporterImportedAt: int = -1
        self.ReporterCorrectlyImported: bool = False

        self.relative_imports = relative_imports
        self.reporter_module_path = reporter_module_path
        self.scope_stack: List[str] = []

        self.calls: Dict[str, List[models.ReporterCall]] = {}
        self.decorators: Dict[str, List[models.ReporterDecorator]] = {}

    # TODO(yhtiyar) also add checking with 'import'
    def matches_with_package_import(self, node: cst.ImportFrom):
        return m.matches(
            node.module,
            m.Attribute(
                value=m.Name(
                    #TODO: Refactor this
                    value=self.reporter_module_path.rsplit('.', 1)[0]  # checking for reporter module path basename
                ),
                attr=m.Name(
                    value="report"
                ),
            ),
        )

    def matches_reporter_call(self, node: cst.Call):
        return m.matches(
            node,
            m.Call(
                func=m.Attribute(
                    value=m.Name(
                        value=self.ReporterImportedAs
                    ),
                ),
            ),
        )

    def matches_with_reporter_decorator(self, node: cst.Decorator):
        return m.matches(
            node,
            m.Decorator(
                decorator=m.Attribute(
                    value=m.Name(
                        value=self.ReporterImportedAs
                    ),
                )
            )
        )

    def visit_FunctionDef(self, node: cst.FunctionDef):
        self.scope_stack.append(node.name.value)
        for decorator in node.decorators:
            if self.matches_with_reporter_decorator(decorator):
                position = self.get_metadata(cst.metadata.PositionProvider, decorator)
                decorator_model = models.ReporterDecorator(
                    decorator_type=decorator.decorator.attr.value,
                    scope_stack=".".join(self.scope_stack),
                    lineno=position.start.line
                )
                self.decorators\
                    .setdefault(decorator.decorator.attr.value, [])\
                    .append(decorator_model)
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

    def check_alias_for_reporter(self, import_aliases, position):
        for alias in import_aliases:
            name = alias.name.value
            if name == "reporter":
                asname = alias.asname
                if asname:
                    self.ReporterImportedAs = asname.name.value
                else:
                    self.ReporterImportedAs = name
                self.ReporterImportedAt = position.start.line
                self.ReporterCorrectlyImported = position.start.line == self.last_import_lineno + 1

    def visit_ImportFrom(self, node: cst.ImportFrom) -> Optional[bool]:
        if self.scope_stack:
            return False
        position = self.get_metadata(cst.metadata.PositionProvider, node)
        if self.relative_imports:
            expected_level = 0
            for character in self.reporter_module_path:
                if character == ".":
                    expected_level += 1
                else:
                    break
            node_import_level = 0
            for dot in node.relative:
                if isinstance(dot, cst.Dot):
                    node_import_level += 1
                else:
                    break
            if (
                    node_import_level == expected_level
                    and node.module.value == self.reporter_module_path[expected_level:]
            ):
                import_aliases = node.names
                self.check_alias_for_reporter(import_aliases, position)

        elif self.matches_with_package_import(node):
            import_aliases = node.names
            self.check_alias_for_reporter(import_aliases, position)

        self.last_import_lineno = position.end.line

    def visit_Call(self, node: cst.Call) -> Optional[bool]:
        if self.ReporterImportedAt == -1:
            return
        if self.matches_reporter_call(node):
            position = self.get_metadata(cst.metadata.PositionProvider, node)
            call_model = models.ReporterCall(
                call_type=node.func.attr.value,
                lineno=position.start.line,
                scope_stack=".".join(self.scope_stack)
            )
            self.calls.setdefault(node.func.attr.value, []).append(call_model)
