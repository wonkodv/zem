import logging
import neovim
import os
import pathlib
import re
import time
import traceback
import threading

from .db import DB
from . import scanner
from . import complete
from pathlib import Path

from .query import tokenize, tokens_to_string

VERSION = '0.4'

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
                    msg=msg.format(*self.args)
                except (IndexError, ValueError):
                    msg = msg + repr(self.args)
        return msg

logging.setLogRecordFactory(BetterLogRecord)

@neovim.plugin
class Plugin(object):
    # Keys that cause an Action
    SPECIAL_KEYS = {
            "<up>"  :"up",
            "<down>":"down",
            "<c-u>" :"update",
            "<c-t>" :"types",
    }
    # mapped keys in the comand Prompt (not re-maped to special keys, but to normal command-line actions)
    REMAPED_KEYS = {
            "<tab>" :"<END> -tab  <CR>",
            "<c-p>" :"<END> -prev <CR>",
            "<c-j>" :"<DOWN>",
            "<c-k>" :"<UP>",
    }

    def __init__(self, nvim):
        self.nvim = nvim
        self.buffer = None
        log_level = self.setting("loglevel", logging.INFO)
        if isinstance(log_level, str):
            log_level = getattr(logging, log_level.upper(), logging.INFO)
        logging.getLogger('zem').setLevel(log_level)

        self.logger = logging.getLogger(__name__).getChild(type(self).__qualname__)
        self.logger.debug("setting LogLevel on zem to {}", log_level)

        self._db = None

    def on_error(self):
        self.logger.exception("Exception occured")
        lines = traceback.format_exc()
        lines = lines.split("\n")
        try:
            self.set_buffer_lines(lines)
        except TypeError:
            pass

    def setting(self, key, default):
        try:
            return self.nvim.vars.get("zem_{}".format(key), default)
        except neovim.NvimError as e:
            return default

    def cmd(self, cmd):
        self.nvim.command(cmd)

    def get_db(self):
        """Lazy get db handle for current cwd/g:zem_db."""
        loc = self.setting("db",".zem.sqlite")
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
        self.update_index()
        t = time.perf_counter() - t
        s = self.get_db().get_size()
        self.nvim.out_write("echomsg 'Scanned {} elements in {:.3f} seconds'\n".format(s,t))

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
        self.buffer.name = "ZEM"
        self.cmd("setlocal winminheight=1")
        self.cmd("setlocal buftype=nofile")
        self.cmd("setlocal noswapfile")
        self.cmd("setlocal nowrap")
        self.cmd("setlocal nonumber")
        self.cmd("setlocal nolist")
        self.cmd("setlocal cursorline")
        self.cmd("setlocal nocursorcolumn")
        self.cmd("setlocal scrolloff=0")
        self.cmd("setlocal filetype=zem_preview") #TODO: add FT file
        self.cmd("wincmd J")
        self.cmd("redraw")
        for k,r in self.REMAPED_KEYS.items():
            self.cmd("cnoremap <buffer> {} {}".format(k,r))
        for k,r in self.SPECIAL_KEYS.items():
            self.cmd("cnoremap <buffer> {} <LT>{}>".format(k,r)) # Special keys just type <action>
        if not default_text:
            self.set_buffer_lines_with_usage([])

        self.nvim.funcs.inputsave()
        try:
            text = self.nvim.funcs.input({
                'prompt':self.setting("prompt",'ZEM> '),
                'highlight':'ZemOnKey',
                'default': default_text,
            })
            line = self.nvim.funcs.line('.')
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
            self.nvim.command('echo {}'.format(repr(exc))) # poor man's str escape
            return

        match = None
        idx = line - 1
        if text:
            tokens = tokenize(text)
            if tokens:
                try:
                    if tokens != self._last_fetched_tokens:
                        matches = self.get_db().get(tokens, limit=1)[0]
                    else:
                        match = self.candidates[idx]
                except (AttributeError, IndexError):
                    match = None

        if match:
            cmd = "edit"
            for t,v in tokenize(text, ignore=()):
                if t.attribute == 'option':
                    if v == 'tab':
                        cmd = "tabedit"
                    elif v == 'prev':
                        cmd = "pedit"
                    else:
                        raise ValueError("Unknown Option ", v)
            self.command_with_match(cmd, match)

    @neovim.function("ZemOnKey",sync=True)
    def zem_on_key(self, args):
        """This is the `highlight` argument of `input()` and is called on every key.

        args is `[ inputText ]`

        return a list of highlight options for the input string
        """
        text, = args
        self.process(text)
        return []

    @neovim.function("ZemGetMatches", sync=True)
    def zem_get_matches(self, args):
        if not ( 1 <= len(args) <= 2):
            raise TypeError("1 or 2 arguments expected")
        q = args[0]
        if len(args) == 2:
            limit = args[1]
        else:
            limit = None
        m = self.get_db().get(tokenize(q), limit=limit)
        return [ dict(r) for r in m ]

    @neovim.function("ZemGetCompletions", sync=True)
    def zem_get_completions(self, args):
        q, limit = args
        res = []
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
                    self.nvim.input("<BS>"*(len(action)+2)) # remove <action>
                    self.action(action)
            else:
                self.nvim.async_call(self.fetch_matches, text)
        except:
            self.on_error()

    def format_match(self, row):
        fn = row['file'][-50:]
        loc = row['location']
        if loc:
            loc = ":"+loc[:20]
        else:
            loc = ""
        extra = row['extra']
        if extra:
            pass
        else:
            extra = ""
        return "{row[name]:35s} {row[type]:15} {fn:>30}{loc:20} {extra}".format(row=row, loc=loc, extra=extra, fn=fn)

    def fetch_matches(self, text):
        """ Trigger an Updatet of the matches in the preview window. """

        tokens = tokenize(text)
        if not any(tokens):
            self.set_buffer_lines_with_usage(["== Nothing to Display ==", "Enter a Query"])
            return

        if tokens == self._last_triggered_tokens:
            self.logger.debug("Ignore Update for %r", tokens)
        else:
            db = self.get_db()
            self._last_triggered_tokens = tokens
            self.logger.info("Trigger Update: %r", tokens)
            self.set_buffer_lines_with_usage(["== Fetching ==", tokens_to_string(tokens)])
            db.interrupt()
            db.get_async(
                tokens=tokens,
                limit=self.setting('result_count', 20),
                callback=self.fetch_matches_cb)

    def fetch_matches_cb(self, result, tokens):
        self.nvim.async_call(self.update_matches, result, tokens)

    def update_matches(self, matches, tokens):
        self.logger.info("Update matches: %d %r", len(matches), tokens)

        matches = tuple(reversed(matches))

        self._last_fetched_tokens = tokens
        self.candidates = matches

        if not matches:
            self.set_buffer_lines([
                "== No Matches ==",
                "Maybe update the Database with <C-U>?",
                "tokens: {}".format(tokens_to_string(tokens))
            ])
        else:
            markup = self.setting("format", self.format_match)
            self.set_buffer_lines([ markup(r) for r in matches])

    def action(self, action):
        """Perform the action caused by special keys."""
        if action == 'up':
            self.cmd("normal k")
            self.cmd("redraw")
        elif action == 'down':
            self.cmd("normal j")
            self.cmd("redraw")
        elif action == 'update':
            self.set_buffer_lines(["Updating..."])
            t = time.perf_counter()
            self.update_index()
            t = time.perf_counter() - t
            s = self.get_db().get_size()
            i = self.get_db().get_stat()
            self.set_buffer_lines(["Found {} elements in {:.3f} seconds".format(s,t),
                *(" {:20s} {:5d}".format(r['type'], r['cnt']) for r in i)])
            self._last_fetched_tokens = None # allow update after the BS are sent
        elif action == 'types':
            types = self.get_db().get_types()
            self.set_buffer_lines( [
                "There are {} types:".format(len(types)),
                *("    "+t for t in types)
                ])
        else:
            raise ValueError("unknown action",action,key,text)

    def command_with_match(self, command, match):
        l = match['location']
        if l:
            if l[-1] == l[0] == '/':
                l = l[1:-1]
                l = "\M"+l # use  nomagic mode, where only ^ $ / and \ are special
                #l = l.replace(match['name'],"\\zs"+match['name']) # search for identifier, not start of line (not supported by nvim yet)
                l = l.replace("\t","\\t") # turn tab cahracters into \t regex
                l = l.replace("\\","\\\\").replace("/","\\/").replace(" ","\\ ") # escape backslashes slashes and spaces for +cmd
                l = r"+/{}/".format(l)
            else:
                l = "+" + l
        else:
            l = ""
        cmd = "{} {} {}".format(command, l, match['file'])
        try:
            self.nvim.vars['zem_command'] = cmd
            self.cmd(cmd)
            self.cmd("nohlsearch")
        except neovim.NvimError:
            pass # something like ATTENTION, swapfile or so..

    def set_buffer_lines(self, lines):
        if not self.buffer:
            raise TypeError("Setting buffer Lines when buffer is closed")
        if not self.nvim.current.buffer == self.buffer:
            raise TypeError("Setting buffer Lines but not in ZEM Buffer")
        self.buffer[:] = lines
        self.cmd("{}wincmd _".format(min(len(lines), self.setting('height',25 ))))
        self.cmd("normal G")   # select first result
        self.cmd("redraw")

    def set_buffer_lines_with_usage(self, lines):
        db = self.get_db()
        lines = USAGE.format(VERSION, db.location, db.get_size()).split("\n")+[""] + lines
        self.set_buffer_lines(lines)

    def update_index(self):
        os.chdir(self.nvim.funcs.getcwd()) # Make paths in scanners relative to buffer's cwd
        data=[]
        info=[]
        for source, param in self.setting("sources", [['files',{}],['tags',{}]]):
            base_param = self.setting("source_{}".format(source), {}).copy()
            base_param.update(param)

            func = getattr(scanner, source, None)
            if func:
                d = func(base_param)
            else:
                d = self.nvim.call(source, base_param)
            data.append(d)

        self.get_db().fill(data)
