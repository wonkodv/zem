import logging
import os
import pathlib
import queue
import re
import threading
import time
import traceback

import neovim

from . import complete, scanner
from .db import DB
from .query import tokenize, tokens_to_string

VERSION = "0.5"

USAGE = """== ZEM v{} ==
Query Syntax:
    WORD    fuzzy match against Name
    =WORD   prefix match against types. Multiple Types enlarge the ResultSet
    :WORD   fuzzy match against Extra (e.g. surronding class, ...)
    WO/RD   fuzzy match against Path
    !WORD   exact match against name
Special Keys:
    <ESC>       Stop ZEM, don't change location
    <UP>/<DOWN> Change selected match
    <CR>        Open the selected match
    <TAB>/<C-P> Open the selected match in a new Tab / PreviewWindow
    <C-U>       ReBuild the Database
    <C-T>       Show all available Types
Using DataBase {} ({} Rows)"""


class BetterLogRecord(logging.LogRecord):
    def getMessage(self):
        msg = str(self.msg)
        if self.args:
            try:
                msg = msg % self.args
            except TypeError:
                try:
                    msg = msg.format(*self.args)
                except (IndexError, ValueError):
                    msg = msg + repr(self.args)
        return msg


logging.setLogRecordFactory(BetterLogRecord)


def thread_excepthook(typ, val, tb, thr):
    logging.getLogger("threading").exception(val)


threading.excepthook = thread_excepthook


@neovim.plugin
class Plugin(object):
    # Keys that cause an Action
    SPECIAL_KEYS = {
        "<up>": "up",
        "<down>": "down",
        "<c-u>": "update",
        "<c-t>": "types",
    }
    # mapped keys in the comand Prompt (not re-maped to special keys, but to
    # normal command-line actions)
    REMAPED_KEYS = {
        "<tab>": "<END> -tab  <CR>",
        "<c-p>": "<END> -prev <CR>",
        "<c-j>": "<DOWN>",
        "<c-k>": "<UP>",
    }

    def __init__(self, nvim):
        self.nvim = nvim
        self.buffer = None
        log_level = self.setting("loglevel", logging.DEBUG)
        if isinstance(log_level, str):
            log_level = getattr(logging, log_level.upper(), logging.DEBUG)
        logging.getLogger("zem").setLevel(log_level)

        self.logger = logging.getLogger(__name__).getChild(type(self).__qualname__)
        self.logger.debug("setting LogLevel on zem to {}", log_level)

        self._db = None

    def on_error(self):
        self.logger.exception("Exception occured")
        ex = traceback.format_exc()
        self.nvim.async_call(self.nvim.err_write, ex)

    def setting(self, key, default):
        try:
            return self.nvim.vars.get("zem_{}".format(key), default)
        except neovim.NvimError:
            return default

    def cmd(self, cmd):
        self.nvim.command(cmd)

    def get_db(self):
        """Lazy get db handle for current cwd/g:zem_db."""
        loc = self.setting("db", ".zem.sqlite")
        if loc != ":memory:":
            loc = pathlib.Path(loc)
            if not loc.is_absolute():
                # can not skip this because plugin has different cwd
                loc = pathlib.Path(self.nvim.funcs.getcwd()) / loc
            loc = loc.absolute()
            loc = str(loc)

        db = self._db
        if db is not None:
            if loc == db.location:
                return db
            db.close()
        db = self._db = DB(loc)
        return db

    @neovim.command("ZemUpdateIndex", sync=False)
    def zem_update_index(self, *args):
        """Fill the database."""
        t = time.perf_counter()

        def cb(count):
            d = time.perf_counter() - t
            self.nvim.out_write(
                f"echomsg 'Scanned {count} elements in {d:.3f} seconds'\n"
            )

        self.update_index(cb)

    @neovim.command("ZemEdit", nargs="1", sync=True)
    def zem_edit(self, args):
        assert len(args) == 1
        arg = args[0]
        m = self.get_db().get(tokenize(arg), limit=1)
        if m:
            self.command_with_match("edit", m[0])

    @neovim.command("ZemTabEdit", nargs="1", sync=True)
    def zem_edit_tab(self, args):
        assert len(args) == 1
        arg = args[0]
        m = self.get_db().get(tokenize(arg), limit=1)
        if m:
            self.command_with_match("tabedit", m[0])

    @neovim.command("ZemPreviewEdit", nargs="1", sync=True)
    def zem_edit_prev(self, args):
        assert len(args) == 1
        arg = args[0]
        m = self.get_db().get(tokenize(arg), limit=1)
        if m:
            self.command_with_match("pedit", m[0])

    @neovim.command("Zem", nargs="?", sync=True)
    def zem_prompt(self, args):
        """Open the ZEM> Prompt."""
        self.candidates = []
        self._last_triggered_tokens = None
        self._last_fetched_tokens = None
        default_text = " ".join(args)

        self.previous_window = self.nvim.current.window

        self.cmd("wincmd n")
        self.zem_window = self.nvim.current.window
        self.buffer = self.nvim.current.buffer
        try:
            self.buffer.name = "ZEM"
        except neovim.NvimError:
            self.cmd("edit ZEM")
        self.cmd("setlocal winminheight=1")
        self.cmd("setlocal buftype=nowrite")  # TODO: buftype=prompt
        self.cmd("setlocal bufhidden=delete")
        self.cmd("setlocal noswapfile")
        self.cmd("setlocal nowrap")
        self.cmd("setlocal nonumber")
        self.cmd("setlocal nohlsearch")
        self.cmd("setlocal nolist")
        self.cmd("setlocal cursorline")
        self.cmd("setlocal nocursorcolumn")
        self.cmd("setlocal scrolloff=0")
        self.cmd("setlocal filetype=zem_preview")  # TODO: add FT file
        self.cmd("{}wincmd _".format(self.setting("height", 25)))
        self.cmd("wincmd J")
        self.cmd("redraw")
        for k, r in self.REMAPED_KEYS.items():
            self.cmd("cnoremap <buffer> {} {}".format(k, r))
        for k, r in self.SPECIAL_KEYS.items():
            # Special keys just type <action>
            self.cmd("cnoremap <buffer> {} <LT>{}>".format(k, r))
        if not default_text:
            self.set_buffer_lines_with_usage([])

        self.nvim.funcs.inputsave()
        try:
            text = self.nvim.funcs.input(
                {
                    "prompt": self.setting("prompt", "ZEM> "),
                    "highlight": "ZemOnKey",
                    "default": default_text,
                }
            )
            line = self.nvim.funcs.line(".")
            exc = None
        except KeyboardInterrupt:
            return
        except neovim.NvimError as e:
            exc = e
        finally:
            self.get_db().interrupt()
            self.close_zem_buffer()
            self.nvim.funcs.inputrestore()
            self.nvim.current.window = self.previous_window
            self.cmd("redraw")

        if exc:
            self.logger.error(exc)
            exc = repr(exc)
            self.nvim.command("echo {}".format(repr(exc)))  # poor man's str escape
            return

        match = None
        idx = line - 1
        if text:
            tokens = tokenize(text)
            if tokens:
                try:
                    if tokens != self._last_fetched_tokens:
                        match = self.get_db().get(tokens, limit=1)[0]
                    else:
                        match = self.candidates[idx]
                except (AttributeError, IndexError):
                    match = None

        if match:
            cmd = "edit"
            for t, v in tokenize(text, ignore=()):
                if t.attribute == "option":
                    if v == "tab":
                        cmd = "tabedit"
                    elif v == "prev":
                        cmd = "pedit"
                    else:
                        raise ValueError("Unknown Option ", v)
            self.command_with_match(cmd, match)

    @neovim.function("ZemOnKey", sync=True)
    def zem_on_key(self, args):
        """OnKey Callback.

        This function is the `highlight` argument of `input()` which seems
        to be the best way for a callback called on every text change.
        args is `[ inputText ]`

        return a list of highlight options for the input string
        """
        (text,) = args
        self.process(text)
        return []

    @neovim.function("ZemGetMatches", sync=True)
    def zem_get_matches(self, args):
        if not (1 <= len(args) <= 2):
            raise TypeError("1 or 2 arguments expected")
        q = args[0]
        if len(args) == 2:
            limit = args[1]
        else:
            limit = None
        m = self.get_db().get(tokenize(q), limit=limit)
        return [dict(r) for r in m]

    @neovim.function("ZemGetCompletions", sync=True)
    def zem_get_completions(self, args):
        q, limit = args
        db = self.get_db()
        cwd = pathlib.Path(db.location).parent
        matches = db.get(tokenize(q), limit=limit)
        return complete.completion_results(matches, cwd)

    def close_zem_buffer(self):
        """Close the ZEM Window."""
        self.cmd("{}bd".format(self.buffer.number))
        self.buffer = None

    _SPECIAL_KEY_RE = re.compile("<([a-z_]*)(>)?")

    def process(self, text):
        """Update the list of matches and process Special Keys.

        called syncronously with the current content of the ZEM Prompt

        Special keys are handled by a mapping in the prompt that inserts
        <key> when a special key is pressed.
        This function performs the action for the key and sends key-strokes to
        remove the sequence.

        If the prompt does not contain a special-key-sequence, is not empty or
        invalid (a single `=`), schedules async Update of the preview window.
        """
        try:
            m = self._SPECIAL_KEY_RE.search(text)
            if m:
                action, complete = m.groups()
                if complete:
                    # remove <action>
                    self.nvim.input("<BS>" * (len(action) + 2))
                    self.action(action)
            else:
                self.nvim.async_call(self.fetch_matches, text)
        except BaseException:
            self.on_error()

    def format_match(self, row):
        fn = row["file"][-100:]
        loc = row["location"]
        if loc:
            loc = ":" + loc[:10]
        else:
            loc = ""
        extra = row["extra"]
        if extra:
            pass
        else:
            extra = ""
        return f"{row['name']:20s} {row['type']:15} {fn:>90}{loc:20}" # {extra}"

    def fetch_matches(self, text):
        """Trigger an Updatet of the matches in the preview window."""

        if self.buffer is None:
            return  # the Zem Buffer was closed since the async call to this function was queued

        tokens = tokenize(text)
        if not any(tokens):
            self.set_buffer_lines_with_usage(
                ["== Nothing to Display ==", "Enter a Query"]
            )
            return

        if tokens == self._last_triggered_tokens:
            self.logger.debug("Ignore Update for %r", tokens)
        else:
            db = self.get_db()
            self._last_triggered_tokens = tokens
            self.logger.info("Trigger Update: %r", tokens)
            self.set_buffer_lines_with_usage(
                ["== Fetching ==", tokens_to_string(tokens)]
            )
            db.interrupt()
            db.get_async(
                tokens=tokens,
                limit=self.setting("result_count", 20),
                callback=self.fetch_matches_cb,
            )

    def fetch_matches_cb(self, result, tokens):
        self.nvim.async_call(self.update_matches, result, tokens)

    def update_matches(self, matches, tokens):
        if self.buffer is None:
            return  # the Zem Buffer was closed since the async call to this function was queued

        self.logger.info("Update matches: %d %r", len(matches), tokens)

        matches = tuple(reversed(matches))

        self._last_fetched_tokens = tokens
        self.candidates = matches

        if not matches:
            self.set_buffer_lines(
                [
                    "== No Matches ==",
                    "Maybe update the Database with <C-U>?",
                    "tokens: {}".format(tokens_to_string(tokens)),
                ]
            )
        else:
            markup = self.setting("format", self.format_match)
            self.set_buffer_lines([markup(r) for r in matches])

    def action(self, action):
        """Perform the action caused by special keys."""
        if action == "up":
            self.cmd("normal k")
            self.cmd("redraw")
        elif action == "down":
            self.cmd("normal j")
            self.cmd("redraw")
        elif action == "update":
            self.set_buffer_lines(["Updating..."])

            t = time.perf_counter()

            def cb(_):
                s = self.get_db().get_size()
                i = self.get_db().get_stat()
                d = time.perf_counter() - t
                self.set_buffer_lines(
                    [
                        "Updating ... Done",
                        f"Found {s} elements in {d:.3f} seconds",
                        *(" {:20s} {:5d}".format(r["type"], r["cnt"]) for r in i),
                    ]
                )
                self._last_triggered_tokens = None
                self._last_fetched_tokens = None

            self.update_index(cb)

        elif action == "types":
            types = self.get_db().get_types()
            self.set_buffer_lines(
                ["There are {} types:".format(len(types)), *("    " + t for t in types)]
            )
        else:
            raise ValueError("unknown action", action)

    def command_with_match(self, command, match):
        l = match["location"]
        if l:
            if l[-1] == l[0] == "/":
                # strip slashes surrounding regex
                l = l[1:-1]

                # use  nomagic mode, where only ^ $ / and \ are special
                l = r"\M" + l

                # l = l.replace(match['name'],"\\zs"+match['name']) # search
                # for identifier, not start of line
                # TODO not supported by nvim yet

                # turn tab characters into \t
                l = l.replace("\t", "\\t")

                # escape backslashes slashes and spaces for +cmd
                l = l.replace("\\", "\\\\")
                l = l.replace("/", "\\/")
                l = l.replace(" ", "\\ ")
                l = r"+/{}/".format(l)
            else:
                l = "+" + l
        else:
            l = ""
        cmd = "{} {} {}".format(command, l, match["file"])
        try:
            self.nvim.vars["zem_command"] = cmd
            self.cmd(cmd)
            self.cmd("nohlsearch")
        except neovim.NvimError:
            pass  # something like ATTENTION, swapfile or so..

    def set_buffer_lines(self, lines):
        if not self.buffer:
            return  # raise TypeError("Setting buffer Lines when buffer is closed")
        if not self.nvim.current.buffer == self.buffer:
            return  # raise TypeError("Setting buffer Lines but not in ZEM Buffer")
        self.buffer[:] = lines
        self.cmd("{}wincmd _".format(min(len(lines), self.setting("height", 25))))
        self.cmd("normal Gzb")  # select first result, scroll it to bottom
        self.cmd("redraw")

    def set_buffer_lines_with_usage(self, lines):
        db = self.get_db()
        lines = (
            USAGE.format(VERSION, db.location, db.get_size()).split("\n") + [""] + lines
        )
        self.set_buffer_lines(lines)

    def update_index(self, callback):
        self.logger.debug("Starting update")
        # Make paths in scanners relative to buffer's cwd
        os.chdir(self.nvim.funcs.getcwd())

        jobs = []
        sources = self.setting("sources", [["files", {}], ["tags", {}]])
        for job_number, (source, param) in enumerate(sources):
            base_param = self.setting("source_{}".format(source), {}).copy()
            base_param.update(param)
            func = getattr(scanner, source)
            name = base_param.get("name") or base_param.get('file') or base_param.get('root') or source
            jobs.append((job_number, name,func, base_param))

        db = self.get_db()

        q = queue.SimpleQueue()

        def do_scan(number, name, func, args):
            self.logger.debug("Starting Job %d: %s", number, name)
            try:
                data = func(args)
                self.logger.debug("Job %d: %s got %d records", number, name, len(data))
            except BaseException:
                self.logger.exception("Job %d: %s got an Exception", number, name, len(data))
                self.on_error()
                data = []
            q.put((number, name, data))


        for number, name, func, arg in jobs:
            self.logger.debug("Starting thread for job %d: %s", number, name)
            t = threading.Thread(
                    target=do_scan, name=f"scan {number} {name}", args=(number, name, func, arg)
            )
            t.start()

        def finish():
            try:
                datas = []
                missing = set(range(len(jobs)))
                count = 0
                while missing:
                    self.logger.debug("Waiting on jobs %r", missing)
                    number, name, data = q.get()
                    missing.remove(number)
                    count += len(data)
                    datas.append(data)
                    self.logger.debug("Recived %d records from %d:%s", len(data), number, name)
                t = time.perf_counter()
                db.fill(datas)
                t = time.perf_counter() - t
                self.logger.info(f"Putting {count} records in the db took {t:.3f}s")
                self.nvim.async_call(callback, count)
            except BaseException as e:
                self.on_error(e)

        threading.Thread(target=finish).start()
