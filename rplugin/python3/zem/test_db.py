import unittest

from .db import DB
from .query import tokenize


class DBTest(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        self.db.fill(
            [
                [
                    # name     type        file    extra       location        prio
                    # subprio
                    ["file.a", "File", "file.a", "", None, 10, 5],
                    ["file.b", "File", "file.b", "", None, 10, 5],
                    ["CONST_A", "Define", "file.a", "str", "/^CONST_A=/", 20, 5],
                    ["CONST_C", "Define", "file.B", "int", 10, 20, 5],
                ],
            ]
        )

    def test_getmatches_simple(self):
        m = self.db.get(tokenize("fla"))
        assert len(m) == 1
        m = m[0]["name"]
        self.assertEqual("file.a", m)

    def test_getmatches_type(self):
        m = self.db.get(tokenize("=De"))
        assert len(m) == 2
        assert all(r[1] == "Define" for r in m)

    def test_getmatches_name_type(self):
        m = self.db.get(tokenize("con =Fi"))
        assert len(m) == 0

    def test_order(self):
        """Test order of matches.

        prio,
        descending match length,
        subprio,
        name
        """
        data = [
            [
                # name     type        file    extra       location        prio
                # subprio
                ["order_2", "typ", "file", "extra", "loc", 0, 2],
                ["order_1", "typ", "file", "extra", "loc", 0, 1],
                ["order_0", "typ", "file", "extra", "loc", 0, 1],
                ["order_0", "typ", "file", "extra", "loc", 1, 1],
                ["order_3", "typ", "file", "extra", "loc", 0, 3],
                ["order_4_", "typ", "file", "extra", "loc", 0, 4],
            ],
        ]
        self.db.fill(data)
        m = self.db.get(tokenize("order"))
        expected = ["order_0", "order_3", "order_2", "order_0", "order_1", "order_4_"]
        assert [r[0] for r in m] == expected
