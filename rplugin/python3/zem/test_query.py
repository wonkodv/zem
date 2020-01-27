from .query import tokenize
import unittest

class TokenizeTest(unittest.TestCase):
    def test_tokenize_empty(self):
        t = tokenize(" ")
        assert t == []

    def test_tokenize_simple(self):
        t = tokenize("  aBC =File :ext =Def -opt", ignore=[])

        assert [(tt.attribute, v) for (tt,v) in t] == [
                ("name","aBC"),
                ("type","File"),
                ("extra","ext"),
                ("type","Def"),
                ("option","opt"),
            ]

    def test_tokenize_unfinished_type(self):
        t = tokenize("  aBC =")
        assert [(tt.attribute, v) for (tt,v) in t] == [
                ("name","aBC"),
        ]


