import sqlite3
class DB:
    _SCHEMA = """
        DROP TABLE IF EXISTS zem;

        CREATE TABLE zem (
            match TEXT NOT NULL,
            type  TEXT NOT NULL,
            file  TEXT NOT NULL,
            location TEXT
        );
        CREATE INDEX zem_type ON zem(type);
        """
    _COLUMNS = ['match', 'type', 'file', 'location']

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

    def fill(self, data):
        with self.con as con:
            con.execute("DELETE FROM zem");
            con.executemany("INSERT INTO zem (match, type, file, location) VALUES (?,?,?,?)", data)
            con.commit()
        con.execute("ANALYZE zem")

    def get(self, matches, types, limit=None):
        w, p = self._tokens_to_where_clause(matches, types)
        q = """
            SELECT
                *
            FROM
                zem
            WHERE
                {}
            ORDER BY
                length(match) ASC
            """.format(w)
        if limit:
            q+="""
            LIMIT {:d} """.format(limit)

        return self.con.execute(q, p).fetchall()

    def _tokens_to_where_clause(self, matches, types):
        matches = [ "%{}%".format("%".join(m)) for m in matches ]
        types = [ "{}%".format(t) for t in types ]
        if matches:
            if types:
                c = """ {}
                    AND
                        ({})
                    """.format(
                        " AND ".join(["match LIKE ?"] * len(matches)),
                        " OR ".join(["type LIKE ?"] * len(types))
                    )
            else:
                c = " AND ".join(["match LIKE ?"] * len(matches))
        else:
            if types:
                c = "({})".format(
                        " OR ".join(["type LIKE ?"] * len(types))
                    )
            else:
                c = "1=1"
        return c,matches+types

    def close(self):
        self.con.close()
        self.con = None

    def isOpen(self):
        return self.con is not None
