import unittest
import os.path

from .scanner import *
from .scanner import _translate

class ScanTest(unittest.TestCase):
    def test_translate_wildir(self):
        r, d, n = _translate(["**/bar"])[0]
        assert not n
        assert not d
        assert     r.fullmatch("foo/bar")
        assert     r.fullmatch("bar")
        assert not r.fullmatch("foo")
        assert not r.fullmatch("foo/foo")

    def test_translate_wildir_name(self):
        r, d, n = _translate(["**_test/"])[0]
        assert not n
        assert     d

        assert     r.fullmatch("foo_test")
        assert     r.fullmatch("_test")
        assert     r.fullmatch("foo/bar_test")
        assert not r.fullmatch("foo_test.py")

    def test_translate_dir(self):
        r, d, n = _translate(["foo/"])[0]
        assert not n
        assert     d

        assert     r.fullmatch("foo")
        assert     r.fullmatch("bar/foo")
        assert not r.fullmatch("bar/foo/")
        assert not r.fullmatch("bar/foo/baz")

    def test_translate_name(self):
        r, d, n = _translate(["foo"])[0]
        assert not n
        assert not d

        assert not r.fullmatch("foobar")
        assert not r.fullmatch("barfoo")
        assert not r.fullmatch("foo/bar")
        assert     r.fullmatch("foo")
        assert     r.fullmatch("bar/foo")

    def test_translate_root_name(self):
        r, d, n = _translate(["/foo"])[0]
        assert not n
        assert not d

        assert not r.fullmatch("foobar")
        assert not r.fullmatch("foo/bar")
        assert     r.fullmatch("foo")
        assert not r.fullmatch("bar/foo")

    def test_translate_root_dir(self):
        r, d, n = _translate(["/foo/"])[0]
        assert not n
        assert     d

        assert not r.fullmatch("foobar")
        assert not r.fullmatch("foo/bar")
        assert     r.fullmatch("foo")
        assert not r.fullmatch("bar/foo")

    def test_translate_paren(self):
        r, d, n = _translate(["foo"], parent="bar")[0]
        assert not n
        assert not d

        assert not r.fullmatch("foobar")
        assert not r.fullmatch("foo/bar")
        assert not r.fullmatch("foo")
        assert     r.fullmatch("bar/foo")
        assert     r.fullmatch("bar/baz/foo")

    def test_translate_parent_root(self):
        r, d, n = _translate(["/foo"], parent="bar")[0]
        assert not n
        assert not d

        assert not r.fullmatch("foobar")
        assert not r.fullmatch("foo/bar")
        assert not r.fullmatch("foo")
        assert     r.fullmatch("bar/foo")
        assert not r.fullmatch("bar/baz/foo")

    def test_translate_wildcard(self):
        r, d, n = _translate(["*"])[0]
        assert not n
        assert not d

        assert     r.fullmatch("foobar")
        assert     r.fullmatch("foo/bar")
        assert     r.fullmatch("foo")
        assert     r.fullmatch("bar/foo")
        assert     r.fullmatch("bar/baz/foo")

    def test_translate_wildcard_root(self):
        r, d, n = _translate(["/*"])[0]
        assert not n
        assert not d

        assert     r.fullmatch("foobar")
        assert not r.fullmatch("foo/bar")
        assert     r.fullmatch("foo")
        assert not r.fullmatch("bar/foo")
        assert not r.fullmatch("bar/baz/foo")

    def test_translate_wildcard_fn(self):
        r, d, n = _translate(["b*r"])[0]
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

        assert any(r[0].endswith(os.path.basename('test_scan.py')) for r in rows)
        assert not any(r[0].endswith('.pyc') for r in rows)


