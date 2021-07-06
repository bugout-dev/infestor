from typing import Optional

import libcst as cst

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
