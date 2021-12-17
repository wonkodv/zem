import unittest

from .complete import completion_results


class CompletionTest(unittest.TestCase):
    def test_completion_lineno(self):
        m = {"file": __file__, "location": "28", "name": "Hans"}
        c = completion_results([m], None)
        info = c["words"][0]["info"].split("\n")
        assert len(info) == 6
        assert "# TestString" == info[0].strip()
        # info ends with \n so last line is Empty. -2 is #Last ContextLine
        assert "# Last ContextLine" == info[-2].strip()

    def test_completion_regex(self):
        m = {"file": __file__, "location": "/^    # TestString$/", "name": "Hans"}
        c = completion_results([m], None)
        info = c["words"][0]["info"].split("\n")
        assert len(info) == 6
        assert "# TestString" == info[0].strip()
        assert "# Last ContextLine" == info[-2].strip()

    # TestString
    # 2 KEEP TestString on Line 28
    # 3
    # 4
    # Last ContextLine
    # 6
    # 7
