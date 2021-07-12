from typing import Optional, List, Tuple

import libcst.matchers as m
import libcst as cst
import logging

from . import manage


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


class PackageFileVisitor(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)
    last_import_lineno = 0

    def __init__(self, reporter_module_path: str, relative_imports: bool):
        self.ReporterImportedAs: str = ""
        self.ReporterImportedAt: int = -1
        self.ReporterSystemCallAt: int = -1
        self.ReporterExcepthookAt: int = -1
        self.ReporterCorrectlyImported: bool = False

        self.relative_imports = relative_imports
        self.reporter_module_path = reporter_module_path
        self.decorators: List[Tuple[str, str, int]] = []

    def visit_FunctionDef(self, node: cst.FunctionDef):
        for decorator in node.decorators:
            position = self.get_metadata(cst.metadata.PositionProvider, decorator)
            self.decorators.append((decorator.Name.value, node.name.value, position.start.line))
        return False

    def visit_ClassDef(self, node: cst.ClassDef):
        return False
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

    def matches_call(self, node: cst.Call, call_name: str):
        return m.matches(
            node,
            m.Call(
                func=m.Attribute(
                    value=m.Name(
                        value=self.ReporterImportedAs
                    ),
                    attr=m.Name(
                        value=call_name
                    ),
                ),
            ),
        )

    def matches_system_report_call(self, node: cst.Call):
        return self.matches_call(node, manage.CALL_TYPE_SYSTEM_REPORT)

    def matches_setup_excepthook(self, node: cst.Call):
        return self.matches_call(node, manage.CALL_TYPE_SETUP_EXCEPTHOOK)

    def visit_Import(self, node: cst.Import) -> Optional[bool]:
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
        if self.matches_system_report_call(node):
            position = self.get_metadata(cst.metadata.PositionProvider, node)
            self.ReporterSystemCallAt = position.start.line
        elif self.matches_setup_excepthook(node):
            position = self.get_metadata(cst.metadata.PositionProvider, node)
            self.ReporterExcepthookAt = position.start.line
