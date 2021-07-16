import difflib
import unittest
from typing import Optional

import libcst as cst
import libcst.matchers as m

from . import config
from . import transformers
from .operations import add_reporter
from .testcase import InfestorTestCase

source1 = '''
try:
    raise NameError("error")
except SomeError as e:

    print("With as name e")
    reporter.error_report(e)

except MyException as m:

    print("With as name m and some inside expressions")
    if a > 5:
        print("smth")
    else:
        print("lol")

    #some comments

    #intentional new lines
except SomeOtherException:
    print("without as name")
    try:
        raise Exception("inner error")
    except InnerError as K:
        print("inner try/except")

except:
    print("No exception name")

def inside_function(a, b):
    if a == 0:
        try:
            a = a/b
        except:
            print("something went wrong")


'''

source2 = '''
try:
    smt()
except Error as e:
    try:
        smth2()
    except InnerError:
        smth3()
        try:
            level(3)
        except:
            lol()
'''


def matches_error_report_call(node: cst.CSTNode, except_as_name, reporter_imported_as):
    return m.matches(
        node,
        m.Call(
            func=m.Attribute(
                value=m.Name(
                    value=reporter_imported_as
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


def matches_error_report_statement(node: cst.SimpleStatementLine, except_as_name, reporter_imported_as):
    return m.matches(
        node,
        m.SimpleStatementLine(
            body=[m.Expr(
                value=m.MatchIfTrue(
                    lambda value: matches_error_report_call(value, except_as_name, reporter_imported_as)
                )
            )]
        )
    )


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

