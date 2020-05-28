import sqlite3

from .query import TOKEN_TYPES

from .threadworker import ThreadWorkerMixin as TWMI

import logging
import time
import threading
import queue


class DB(TWMI):
    _SCHEMA = """
        DROP TABLE IF EXISTS zem;

        CREATE TABLE zem (
            name        TEXT NOT NULL,
            type        TEXT NOT NULL,
            file        TEXT NOT NULL,
            extra       TEXT,
            location    TEXT,
            prio        INT NOT NULL,
            subprio     INT NOT NULL
        );
        CREATE INDEX zem_type ON zem(type);
        """
    _COLUMNS = ['name', 'type', 'file', 'extra', 'location', 'prio', 'subprio']

    def __init__(self, location):
        self.THREAD_WORKER_NAME=f"DB Worker {location}"
        self.THREAD_WORKER_DAEMON=True
        super().__init__()
        self.location = location
        self._size = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__qualname__}")

        self._check_and_init()

    @TWMI.sync_call
    def _check_and_init(self):
        self.con = sqlite3.connect(self.location)
        self.con.row_factory = sqlite3.Row

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

    @TWMI.sync_call
    def get_size(self):
        if self._size is None:
            self._size = self.con.execute("SELECT COUNT(*) FROM zem;").fetchone()[0]
        return self._size

    @TWMI.sync_call
    def get_stat(self):
        r = self.con.execute("SELECT type, count(name) as cnt FROM zem GROUP BY type;").fetchall()
        return r

    @TWMI.sync_call
    def fill(self, datas, wipe=True):
        self._size = None
        with self.con as con:
            if wipe:
                con.execute("DELETE FROM zem");
            for data in datas: # can pass several iterators
                con.executemany("""
                        INSERT INTO zem 
                                (name, type, file, extra, location, prio, subprio)
                        VALUES (?,     ?,    ?,    ?,     ?,        ?,    ?)""",
                        data)
            con.commit()
        con.execute("ANALYZE zem")

    @TWMI.sync_call
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
                prio DESC,
                length(name) ASC,
                subprio DESC,
                name  ASC,
                type ASC,
                length(file) ASC
            """.format(where)
        if limit:
            q+="""
            LIMIT {:d} """.format(limit)


        t = time.time()
        result = self.con.execute(q, params).fetchall()
        t = time.time() - t

        self.logger.debug("%s, %r in %.2fms", q, params, t/1000)
        return result

    @TWMI.async_call
    def get_async(self, tokens, callback, *, limit=None):
        try:
            result = self.get(tokens, limit)
            callback(tokens=tokens, result=result)
        except sqlite3.OperationalError:
            pass # we were interrupted


    @TWMI.sync_call
    def get_types(self):
        q = """
            SELECT DISTINCT
                type
            FROM
                zem
            ORDER BY
                type ASC
            """
        return [r['type'] for r in self.con.execute(q)]


    def _tokens_to_where_clause(self, tokens):
        and_clauses = []
        and_params = []
        or_clauses = []
        or_params = []
        for typ, val in tokens:
            pos, key, match_type, column, op = typ

            if typ.matchtyp == 'fuzzy':
                val = "%{}%".format("%".join(val))
            elif typ.matchtyp == 'exact':
                pass
            elif typ.matchtyp == 'prefix':
                val = "{}%".format(val)
            elif typ.matchtyp == 'ignore':
                continue
            else:
                raise ValueError("unknown type", match_type)

            if typ.grouping == 'and':
                and_clauses.append("{} LIKE ?".format(column))
                and_params.append(val)
            elif typ.grouping == 'or':
                or_clauses.append("{} LIKE ?".format(column))
                or_params.append(val)

        if or_clauses:
            and_clauses.append("({})".format(" OR ".join(or_clauses)))

        where = " AND ".join(and_clauses)
        params = and_params + or_params
        return where, params

    @TWMI.sync_call
    def close(self):
        self.con.close()
        self.con = None
        self.stop_thredworker()

    def interrupt(self):
        i = 0
        try:
            self._thread_worker._q.get_nowait()
            i += 1
        except queue.Empty:
            pass
        self.con.interrupt()
        self.logger.debug(f" db interrupted, cleared {i} jobs from Q")
