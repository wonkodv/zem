import unittest
import os.path

from .query import tokenize
from .db import DB
from .scanner import *
from .complete import completion_results

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
    def test_translate_wildir(self):
        r, d, n = translate(["**/bar"])[0]
        assert not n
        assert not d
        assert     r.fullmatch("foo/bar")
        assert     r.fullmatch("bar")
        assert not r.fullmatch("foo")
        assert not r.fullmatch("foo/foo")

    def test_translate_wildir_name(self):
        r, d, n = translate(["**_test/"])[0]
        assert not n
        assert     d

        assert     r.fullmatch("foo_test")
        assert     r.fullmatch("_test")
        assert     r.fullmatch("foo/bar_test")
        assert not r.fullmatch("foo_test.py")

    def test_translate_dir(self):
        r, d, n = translate(["foo/"])[0]
        assert not n
        assert     d

        assert     r.fullmatch("foo")
        assert     r.fullmatch("bar/foo")
        assert not r.fullmatch("bar/foo/")
        assert not r.fullmatch("bar/foo/baz")

    def test_translate_name(self):
        r, d, n = translate(["foo"])[0]
        assert not n
        assert not d

        assert not r.fullmatch("foobar")
        assert not r.fullmatch("barfoo")
        assert not r.fullmatch("foo/bar")
        assert     r.fullmatch("foo")
        assert     r.fullmatch("bar/foo")

    def test_translate_root_name(self):
        r, d, n = translate(["/foo"])[0]
        assert not n
        assert not d

        assert not r.fullmatch("foobar")
        assert not r.fullmatch("foo/bar")
        assert     r.fullmatch("foo")
        assert not r.fullmatch("bar/foo")

    def test_translate_root_dir(self):
        r, d, n = translate(["/foo/"])[0]
        assert not n
        assert     d

        assert not r.fullmatch("foobar")
        assert not r.fullmatch("foo/bar")
        assert     r.fullmatch("foo")
        assert not r.fullmatch("bar/foo")

    def test_translate_paren(self):
        r, d, n = translate(["foo"], parent="bar")[0]
        assert not n
        assert not d

        assert not r.fullmatch("foobar")
        assert not r.fullmatch("foo/bar")
        assert not r.fullmatch("foo")
        assert     r.fullmatch("bar/foo")
        assert     r.fullmatch("bar/baz/foo")

    def test_translate_parent_root(self):
        r, d, n = translate(["/foo"], parent="bar")[0]
        assert not n
        assert not d

        assert not r.fullmatch("foobar")
        assert not r.fullmatch("foo/bar")
        assert not r.fullmatch("foo")
        assert     r.fullmatch("bar/foo")
        assert not r.fullmatch("bar/baz/foo")

    def test_translate_wildcard(self):
        r, d, n = translate(["*"])[0]
        assert not n
        assert not d

        assert     r.fullmatch("foobar")
        assert     r.fullmatch("foo/bar")
        assert     r.fullmatch("foo")
        assert     r.fullmatch("bar/foo")
        assert     r.fullmatch("bar/baz/foo")

    def test_translate_wildcard_root(self):
        r, d, n = translate(["/*"])[0]
        assert not n
        assert not d

        assert     r.fullmatch("foobar")
        assert not r.fullmatch("foo/bar")
        assert     r.fullmatch("foo")
        assert not r.fullmatch("bar/foo")
        assert not r.fullmatch("bar/baz/foo")

    def test_translate_wildcard_fn(self):
        r, d, n = translate(["b*r"])[0]
        assert not n
        assert not d

        assert not r.fullmatch("foobar")
        assert     r.fullmatch("foo/bar")
        assert not r.fullmatch("foo")
        assert     r.fullmatch("bar")
        assert not r.fullmatch("bar/baz/foo")
        assert not r.fullmatch("b/a/r")


    def test_scanfiles(self):
        settings = {
            "roots":os.path.dirname(__file__),
            "exclude":["*.pyc"],
            'type':'File',
        }
        rows = files(settings)

        assert any(r[0].endswith('test.py') for r in rows)
        assert not any(r[0].endswith('test.pyc') for r in rows)

class CompletionTest(unittest.TestCase):
    #TestString
    def test_completion_lineno(self):
        m = {'file':__file__, 'location': '197', 'name':'Hans'}
        c = completion_results([m], None)
        info = c['words'][0]['info'].split("\n")
        assert len(info) == 11
        assert "#TestString" == info[7].strip()

    def test_completion_regex(self):
        m = {'file':__file__, 'location': '/^    #TestString$/', 'name':'Hans'}
        c = completion_results([m], None)
        info = c['words'][0]['info'].split("\n")
        assert len(info) == 11
        assert "#TestString" == info[6].strip()



# cd %:h/.. && python3 -m pytest zem/test.py
