import libcst as cst
from typing import Optional, List
import libcst.matchers as m



def matches_import(node: cst.CSTNode) -> bool:
    return m.matches(
        node,
        m.SimpleStatementLine(
            body=[m.Import | m.ImportFrom]
        )
    )


class NakedTransformer(cst.CSTTransformer):
    last_import = None

    def __init__(
            self,
            imports_to_add: Optional[List[str]],
            calls_to_add: Optional[List[str]],
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
        for el in original_node.body:
            new_body.append(el)
            if el == self.last_import:
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
        if self.last_import is None:
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

        return updated_node.with_changes(
            body=new_body
        )
