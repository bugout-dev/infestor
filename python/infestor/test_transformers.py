import difflib
import unittest
from typing import Optional

import libcst as cst
import libcst.matchers as m

from . import config
from . import transformers
from .operations import add_reporter
from .testcase import InfestorTestCase


class TestTryExcept(unittest.TestCase):
    def setUp(self) -> None:
        pass

    def test_simple_try_except(self):
        source_code = """
        """


class TestImportReporterTransformer(InfestorTestCase):
    def setUp(self):
        super().setUp()
        add_reporter(self.package_dir)
        self.config = config.load_config(self.config_file)
        self.package_transformer = transformers.ImportReporterTransformer(
            self.package_dir
        )


if __name__ == "__main__":
    unittest.main()
