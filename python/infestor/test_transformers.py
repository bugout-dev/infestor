import unittest
import libcst as cst
from infestor import transformers
import difflib

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

    #intentional spaces
except SomeOtherException:
    print("without as name")
    try:
        raise Exception("inner error")
    except InnerError as K:
        print("inner try/except")

except:
    print("No exception name")


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


source = source1

source_tree = cst.metadata.MetadataWrapper(cst.parse_module(source))
transformer = transformers.TryCatchTransformer("reporter")
modified_tree = source_tree.visit(transformer)
print(modified_tree.code)

print(
    "".join(
        difflib.unified_diff(source.splitlines(True), modified_tree.code.splitlines(True))
    )
)


