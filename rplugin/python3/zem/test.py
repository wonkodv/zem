import unittest
import os.path

from .plugin import tokenize
from .db import DB
from .scanner import *

class TokenizeTest(unittest.TestCase):
    def test_tokenize_empty(self):
        m,t = tokenize(" ")
        assert m == []
        assert t == []

    def test_tokenize_simple(self):
        m,t = tokenize("  aBC =File HJ =Def")
        assert m == ["aBC","HJ"]
        assert t == ["File","Def"]

    def test_tokenize_unfinished_type(self):
        m,t = tokenize("  aBC =")
        assert m == ["aBC"]
        assert t == []


class DBTest(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        self.db.fill([
            ["file.a","File","file.a",None],
            ["file.b","File","file.b",None],
            ["CONST_A","Define","file.a","/^#define CONST_A/"],
            ["CONST_B","Define","file.B",10],
        ])

    def test_tokenstowhere(self):
        def h(s):
            s,p = self.db._tokens_to_where_clause(*tokenize(s))
            s = s.split()
            s = " ".join(s)
            return s,p

        self.assertEqual(h("abc =D def =Fil j"),
                ('match LIKE ? AND match LIKE ? AND match LIKE ? AND (type LIKE ? OR type LIKE ?)',
                ["%a%b%c%","%d%e%f%","%j%","D%","Fil%"])
            )

    def test_getmatches_simple(self):
        m = self.db.get(*tokenize("fla"))
        assert len(m) == 1
        m = m[0]['match']
        self.assertEqual("file.a", m)

    def test_getmatches_type(self):
        m = self.db.get(*tokenize("=De"))
        assert len(m) == 2
        assert all(r[1] == "Define" for r in m)

    def test_getmatches_simple(self):
        m = self.db.get(*tokenize("con =Fi"))
        assert len(m) == 0

    def test_scanFiles(self):
        data = ["test.py","File","test.py","123"]
        self.db.fill([data])
        m = self.db.get(*tokenize("tst.y"))
        assert list(m[0]) == data

class ScanTest(unittest.TestCase):
    def test_translate(self):
        r = translate([".*", "*.pyc", "/test/**/*.py"])
        assert r.match("foo/.bar")
        assert r.match(".bar")
        assert r.match("foo/bar.pyc")
        assert r.match("foo.pyc")
        assert r.match("test/foo.py")
        assert r.match("test/foo.pyc")
        assert r.match("test/foo/bar.py")
        assert r.match("test/foo/bar/baz.py")

        assert not r.match("foo.py")
        assert not r.match("foo/bar.py")
        assert not r.match("foo/bar.pyc.baz")
        assert not r.match("foo/bar.pyc.baz")
        assert not r.match("foo/test/bar.py")
        assert not r.match("foo/test/bar/baz.py")

    def test_translate_wildir(self):
        r = translate(["**/bar"])
        assert r.match("foo/bar")
        assert r.match("bar")
        assert not r.match("foo")
        assert not r.match("foo/foo")

    def test_translate_wildir_name(self):
        r = translate(["**_test/"])
        assert r.match("foo_test/")
        assert r.match("_test/")
        assert r.match("foo/bar_test/")
        assert not r.match("foo_test.py")

    def test_scanfiles(self):
        settings = {
            "root":os.path.dirname(__file__),
            "pattern":["**/*.*"],
            "exclude":[],
            'type':'File',
        }
        rows = files(settings)

        assert any(r[0].endswith('test.py') for r in rows)

# cd .. && py -3 -m pytest zem/test.py
