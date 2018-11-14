import neovim
import pathlib
import time
import os
import re
from .db import DB
from . import scanner
from . import complete
from pathlib import Path

from .query import tokenize

VERSION = '0.2'

USAGE = """== ZEM v{} ==
Query Syntax:
    WORD    fuzzy match against Name
    :WORD   fuzzy match against Extra (e.g. surronding class, ...)
    /WORD   fuzzy match against Path
    =WORD   prefix match against types. Multiple Types enlarge the ResultSet
Special Keys:
    <ESC>       Stop ZEM, don't change location
    <UP>/<DOWN> Change selected match
    <CR>        Open the selected match
    <TAB>/<C-P> Open the selected match in a new Tab / PreviewWindow
    <C-U>       ReBuild the Database
    <C-T>       Show all available Types
Using DataBase {} ({} Rows)"""

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
        self._db = None
        self.buffer = None

    def on_error(self):
        import traceback
        lines = traceback.format_exc()
        with open(".zem.errors","at") as f:
            f.write(lines)
        lines = lines.split("\n")
        try:
            self.set_buffer_lines(lines)
        except TypeError:
            pass

    def setting(self, key, default):
        return self.nvim.vars.get("zem_{}".format(key), default)

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
        if self._db is not None:
            if loc == self._db.location:
                return self._db
            self._db.close()
        self._db = DB(loc)
        return self._db

    @neovim.command("ZemUpdateIndex", sync=False)
    def zem_update_index(self, *args):
        """Fill the database."""
        t = time.perf_counter()
        i = self.update_index()
        t = time.perf_counter() - t
        s = sum(c for (s,c) in i)
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
        self._last_tokens = None
        self.count = self.setting("height", 20)
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
        self.cmd("setlocal filetype=zem_preview") #TODO: add FT file
        self.cmd("wincmd J")
        self.cmd("redraw")
        for k,r in self.REMAPED_KEYS.items():
            self.cmd("cnoremap <buffer> {} {}".format(k,r))
        for k,r in self.SPECIAL_KEYS.items():
            self.cmd("cnoremap <buffer> {} <LT>{}>".format(k,r)) # Special keys just type <action>
        if not default_text:
            self.set_buffer_lines_with_usage([])

        match = None
        self.nvim.funcs.inputsave()
        try:
            text = self.nvim.funcs.input({
                'prompt':self.setting("prompt",'ZEM> '),
                'highlight':'ZemOnKey',
                'default': default_text,
            })
        except KeyboardInterrupt: # TODO catch nvim error, check text against keyboard interrupt
            text = None
        self.nvim.funcs.inputrestore()

        if text:
            line = self.nvim.funcs.line('.')
            idx = line - 1
            try:
                match = self.candidates[idx]
            except (AttributeError, IndexError):
                pass
            else:
                cmd = "edit"
                for t,v in tokenize(text):
                    if t == 'option':
                        if v == 'tab':
                            cmd = "tabedit"
                        elif v == 'prev':
                            cmd = "pedit"
                        else:
                            raise ValueError("Unknown Option ", v)
        self.close_zem_buffer()
        self.nvim.current.window = self.previous_window
        self.cmd("redraw")
        if match:
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
                self.nvim.async_call(self.update_preview, text)
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

    def update_preview(self, text):
        """Updatet the matches in the preview window.

        The latest result set is cached in `self.candidates`. <UP> and <DOWN> change
        the selected line in the preview window, <TAB> or <CR> use the line
        number to select the candidate and open its file.
        """
        try:
            tokens = tokenize(text, ignore=['option'])
            if tokens == self._last_tokens:  # only query the db if anything changed
                return
            self._last_tokens = tokens
            if not any(tokens):
                self.set_buffer_lines_with_usage(["== Nothing to Display ==", "Enter a Query"])
                return
            results = self.get_db().get(tokens, limit=self.count)
            results = list(reversed(results))
            self.candidates = results
            if not results:
                self.set_buffer_lines([
                    "== No Matches ==",
                    "Maybe update the Database with <C-U>?",
                    "tokens: {}".format(tokens),
                ])
            else:
                markup = self.setting("format", self.format_match)
                self.set_buffer_lines([ markup(r) for r in results])
        except:
            self.on_error()

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
            i = self.update_index()
            t = time.perf_counter() - t
            s = sum(c for (s,c) in i)
            self.set_buffer_lines(["Found {} elements in {:.3f} seconds".format(s,t),
                *("   {:10s} {:5d}".format(s,c) for (s,c) in i)])
            self._last_tokens = None # allow update after the BS are sent
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
                l = r"/\M{}".format(l) # use  nomagic mode, where only ^ $ / and \ are special
                l = l.replace(match['name'],"\\zs"+match['name']) # search for identifier, not start of line (not supported by nvim yet)
                l = l.replace("\\","\\\\").replace(" ","\\ ") # escape backslashes, then escape space
            l = "+" + l
        else:
            l = ""
        cmd = "{} {} {}".format(command, l, match['file'])
        try:
            self.nvim.vars['zem_command'] = cmd
            self.cmd(cmd)
            self.cmd("nohlsearch")
        except neovim.api.nvim.NvimError:
            pass # something like ATTENTION, swapfile or so..

    def set_buffer_lines(self, lines):
        if not self.buffer:
            raise TypeError("Setting buffer Lines when buffer is closed")
        if not self.nvim.current.buffer == self.buffer:
            raise TypeError("Setting buffer Lines but not in ZEM Buffer")
        self.buffer[:] = lines
        self.cmd("{}wincmd _".format(len(lines)))
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
                d = self.nvim.call(source, param)
            info.append((source,len(d)))
            data.extend(d)

        self.get_db().fill(data)
        return info
