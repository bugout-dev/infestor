import difflib
import unittest
from typing import Optional

import libcst as cst
import libcst.matchers as m

from . import config
from . import transformers
from .operations import add_reporter
from .testcase import InfestorTestCase


class CheckExceptHandlerVisitor(cst.CSTVisitor):

    def __init__(self, reporter_imported_as):
        self.reporter_imported_as = reporter_imported_as

    def visit_ExceptHandler(self, node: cst.ExceptHandler) -> Optional[bool]:
        if node.type is None:
            raise Exception("Missing except type")
        asname = None
        try:
            assert isinstance(node.name, cst.AsName)
            assert isinstance(node.name.name, cst.Name)
            asname = node.name.name.value
        except:
            raise Exception("Missing asname of exception")

        has_error_report = False
        for el in node.body.body:
            if (
                isinstance(el, cst.SimpleStatementLine)
                and matches_error_report_statement(el, asname, self.reporter_imported_as)
            ):
                if has_error_report:
                    raise Exception("error_report is called more than once ")
                has_error_report = True
        return True


class TestTryExcept(unittest.TestCase):
    def setUp(self) -> None:
        pass

    def test_simple_try_except(self):
        source_code = '''
        '''


class TestImportReporterTransformer(InfestorTestCase):
    def setUp(self):
        super().setUp()
        add_reporter(self.package_dir)
        self.config = config.load_config(self.config_file)
        self.package_transformer = transformers.ImportReporterTransformer(self.package_dir)



if __name__ == "__main__":
    unittest.main()

