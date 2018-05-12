import sqlite3

from .query import TOKEN_TYPES

class DB:
    _SCHEMA = """
        DROP TABLE IF EXISTS zem;

        CREATE TABLE zem (
            name        TEXT NOT NULL,
            type        TEXT NOT NULL,
            file        TEXT NOT NULL,
            extra       TEXT,
            location    TEXT,
            prio        INT NOT NULL
        );
        CREATE INDEX zem_type ON zem(type);
        """
    _COLUMNS = ['name', 'type', 'file', 'extra', 'location', 'prio']

    def __init__(self, location):
        self.location = location
        self.con = sqlite3.connect(location)
        self.con.row_factory = sqlite3.Row
        self._check_and_init()

    def _check_and_init(self):
        try:
            r = self.con.execute("SELECT * FROM zem LIMIT 1").fetchone()
            ok = False
            if r:
                ok = r.keys() == self._COLUMNS
        except sqlite3.DatabaseError:
            ok = False
        if not ok:
            with self.con as c:
                c.executescript(self._SCHEMA)

    def get_size(self):
        r = self.con.execute("SELECT COUNT(*) FROM zem;").fetchone()
        return r[0]

    def fill(self, data):
        with self.con as con:
            con.execute("DELETE FROM zem");
            con.executemany("INSERT INTO zem (name , type, file, extra, location, prio) VALUES (?,?,?,?,?,?)", data)
            con.commit()
        con.execute("ANALYZE zem")

    def get(self, tokens, limit=None):
        where, params = self._tokens_to_where_clause(tokens)
        q = """
            SELECT
                *
            FROM
                zem
            WHERE
                {}
            ORDER BY
                length(name ) ASC,
                prio DESC,
                name  ASC
            """.format(where)
        if limit:
            q+="""
            LIMIT {:d} """.format(limit)

        return self.con.execute(q, params).fetchall()

    def _tokens_to_where_clause(self, tokens):
        and_clauses = ["1=1"]
        and_params = []
        or_clauses = []
        or_params = []
        for typ, val in tokens:
            _, match_type, column, op = TOKEN_TYPES[typ]

            if match_type == 'fuzzy':
                val = "%{}%".format("%".join(val))
            elif match_type == 'prefix':
                val = "{}%".format(val)
            elif match_type == 'ignore':
                continue
            else:
                raise ValueError("unknown type", match_type)

            if op == 'and':
                and_clauses.append("{} LIKE ?".format(column))
                and_params.append(val)
            elif op == 'or':
                or_clauses.append("{} LIKE ?".format(column))
                or_params.append(val)

        if or_clauses:
            and_clauses.append("({})".format(" OR ".join(or_clauses)))

        where = " AND ".join(and_clauses)
        params = and_params + or_params
        return where, params

    def close(self):
        self.con.close()
        self.con = None

    def isOpen(self):
        return self.con is not None
