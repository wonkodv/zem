import unittest
import os.path

from .query import tokenize
from .db import DB
from .scanner import *

class TokenizeTest(unittest.TestCase):
    def test_tokenize_empty(self):
        t = tokenize(" ")
        assert t == []

    def test_tokenize_simple(self):
        t = tokenize("  aBC =File :ext =Def -opt")
        assert t == [
                ("name","aBC"),
                ("type","File"),
                ("extra","ext"),
                ("type","Def"),
                ("option","opt"),
            ]

    def test_tokenize_unfinished_type(self):
        t = tokenize("  aBC =")
        assert t == [("name","aBC")]


class DBTest(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        self.db.fill([
            # name     type        file    extra       location        prio
            ["file.a",   "File",    "file.a",  "",    None          ,   10 ],
            ["file.b",   "File",    "file.b",  "",    None          ,   10 ],
            ["CONST_A",  "Define",  "file.a",  "str", "/^CONST_A=/" ,   20 ],
            ["CONST_B",  "Define",  "file.B",  "int", 10            ,   20 ],
        ])

    def test_getmatches_simple(self):
        m = self.db.get(tokenize("fla"))
        assert len(m) == 1
        m = m[0]['name']
        self.assertEqual("file.a", m)

    def test_getmatches_type(self):
        m = self.db.get(tokenize("=De"))
        assert len(m) == 2
        assert all(r[1] == "Define" for r in m)

    def test_getmatches_simple(self):
        m = self.db.get(tokenize("con =Fi"))
        assert len(m) == 0

    def test_order(self):
        "Test, that matches are sorted by decreasing mathc-length, then by prio"
        data = [
                # name     type        file    extra       location        prio
                [ "order_2", "typ", "file",     "extra",    "loc",          2],
                [ "order_1", "typ", "file",     "extra",    "loc",          1],
                [ "order_3", "typ", "file",     "extra",    "loc",          3],
                [ "order_4_", "typ", "file",     "extra",    "loc",         4],
            ]
        self.db.fill(data)
        m = self.db.get(tokenize("order"))
        assert [r[0] for r in m] == ["order_3", "order_2", "order_1", "order_4_"]

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
