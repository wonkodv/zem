import neovim
import re
import pathlib
import time
from .db import DB
from . import scanner

VERSION = '0.1'

USAGE = """== ZEM v{} ==
Query Syntax:
    WORD    match all characters of this word in order, not necessarily adjacent.
            all entered WORDs must match, but in any order
    =TYPE   match types that start with TYPE
            must match any type, if multiple are entered
Special Keys:
    <ESC>       Stop ZEM, don't change location
    <UP> <DOWN> Change selected match
    <CR>        Open the selected match
    <TAB>       Open the selected match in a new tab
    <C-U>       ReBuild the Database
Using DataBase {} """


@neovim.plugin
class Plugin(object):
    def __init__(self, nvim):
        self.nvim = nvim
        self.db = None

    def setting(self, key, default):
        return self.nvim.vars.get("zem_{}".format(key), default)

    def _get_db(self):
        db_location = pathlib.Path(self.setting("db",".zem.sqlite"))
        if not db_location.is_absolute():
            db_location = pathlib.Path(self.nvim.funcs.getcwd()) / db_location
        return DB(str(db_location))

    @neovim.command("Zem", sync=True)
    def prompt(self, *args):
        """Open the ZEM> Prompt."""
        self.db = self._get_db()
        self.candidates = []
        self._last_tokens = None
        self.count = self.setting("height", 20)
        self.open_window()

        self.nvim.funcs.inputsave()
        try:
            self.nvim.funcs.input({
                'prompt':self.setting("prompt",'ZEM> '),
                'highlight':'ZemOnKey'
            })
        finally:
            self.nvim.funcs.inputrestore()
        self.close_window()
        self.db.close()
        self.db = None

    def open_window(self):
        """Open the ZEM Window"""
        self.nvim.command("wincmd n")
        self.buffer = self.nvim.current.buffer
        self.nvim.command("setlocal winminheight=1")
        self.nvim.command("setlocal buftype=nofile")
        self.nvim.command("setlocal bufhidden=delete")
        self.nvim.command("setlocal noswapfile")
        self.nvim.command("setlocal nobuflisted")
        self.nvim.command("setlocal nonumber")
        self.nvim.command("setlocal nolist")
        self.buffer.name = "ZEM"
        self.nvim.command("wincmd J")
        self.nvim.command("redraw")
        for k in "up down tab cr c-u".split():
            self.nvim.command("cnoremap <buffer> <{0}> ${0}$".format(k)) # Special keys just add a $KEY$ sequence
        self.set_buffer_usage([])
    @neovim.function("ZemOnKey",sync=True)
    def on_key(self, args):
        """This is the `highlight` argument of `input()` and is called on every key.

        args is `[ inputText ]`

        return a list of highlight options for the input string
        """
        text, = args
        self.nvim.async_call(self.process, text)
        return []

    def close_window(self):
        """Try closing the ZEM Window."""
        if self.buffer.valid:
            try:
                self.nvim.command("{}bd".format(self.buffer.number))
                self.nvim.command("redraw")
            except neovim.api.nvim.NvimError:
                pass # probably already deleted

    def process(self, text):
        """Update the list of matches and process Special Keys.

        called asyncronously with the current content of the ZEM Prompt

        Special keys are handled by a mapping in the prompt that inserts
        $key$ when a special key is pressed.
        This function performs the action for the key and sends key-strokes to
        remove the sequence.

        If the prompt does not contain a special-key-sequence, is not empty or
        invalid (a single `=`), the db is queried for matches and they are
        inserted into the Preview Window.

        The latest result set is cached in `self.candidates`. <UP> and <DOWN> change
        the selected line in the preview window, <TAB> or <CR> use the line
        number to select the candidate and open its file.
        """
        if '$' in text:
            _, d, t = text.partition("$")
            key, d, _ = t.partition("$")
            if d:
                remove = True
                if key == 'up':
                    self.nvim.command("normal k")
                    self.nvim.command("redraw")
                elif key == 'down':
                    self.nvim.command("normal j")
                    self.nvim.command("redraw")
                elif key == 'c-u':
                    self.set_buffer(["Updating..."])
                    t = time.perf_counter()
                    l = self._update_index()
                    t = time.perf_counter() - t
                    self.set_buffer(["Scanned {} elements in {:.3f} seconds".format(l,t)])
                elif key in ['cr','tab']:
                    line = self.nvim.funcs.line('.')
                    self.nvim.input("<ESC>")            # finish the input() prompt
                    self.close_window()                 # destroy the zem window
                    remove = False
                    idx = line - 1
                    if not self.candidates:
                        return
                    m = self.candidates[idx]
                    cmd = "edit"
                    l = m['location']
                    if l:
                        for s in "\\ []":
                            l = l.replace(s, "\\"+s) # TODO: proper escape
                        cmd += " +" + l
                    if key == 'tab':
                        cmd = 'tab' + cmd
                    cmd = cmd + " " + m['file']
                    self.nvim.command("echomsg '{}'".format(cmd))
                    try:
                        self.nvim.command(cmd)
                    except neovim.api.nvim.NvimError:
                        pass # something like ATTENTION, swapfile or so..
                else:
                    self.set_buffer_usage(["== Unknown Key ==", "detexted {} in {}.".format(key,text)])
                    remove = False
                if remove:
                    self.nvim.input("<BS>"*(len(key)+2)) # remove $key$
        else:
            t = tokenize(text)
            if t == self._last_tokens:  # only query the db if anything changed
                return
            if not any(t):
                self.set_buffer_usage(["== Nothing to Display ==", "Enter a Query"])
                return
            self._last_tokens = t
            results = self.db.get(*t, limit=self.count)
            results = list(reversed(results))
            self.candidates = results
            if not results:
                self.set_buffer([
                    "== No Matches ==",
                    "Maybe update the Database with <C-U>?",
                    "words: {}".format(t[0]),
                    "types: {}".format(t[1])]
                )
            else:
                self.set_buffer([ r['match'] for r in results])

    def set_buffer_usage(self, lines):
        lines = USAGE.format(VERSION, self.db.location).split("\n")+[""] + lines
        self.set_buffer(lines)

    def set_buffer(self, lines):
        self.buffer[:] = lines
        self.nvim.command("{}wincmd _".format(len(lines)))
        self.nvim.command("normal G")   # select first result
        self.nvim.command("redraw")

    @neovim.command("ZemUpdateIndex", sync=True)
    def update_index(self, *args):
        """Fill the database."""
        t = time.perf_counter()
        l = self._update_index()
        t = time.perf_counter() - t
        self.nvim.command("echomsg 'Scanned {} elements in {:.3f} seconds'".format(l,t))

    def _update_index(self):
        sources = []
        for source in self.setting("sources", ['files','tags']):
            func = getattr(scanner, source, None)
            if not func:
                func = self.nvim.funcs[func]
            param = self.setting("source_{}".format(source), {})
            sources.append((func, param))
        data=[]
        for func, param in sources:
            data += func(param)

        if self.db is None:
            db = self._get_db()
            db.fill(data)
            db.close()
        else:
            self.db.fill(data)
        return len(data)

def tokenize(text):
    matches = []
    types   = []
    for p in text.split():
        if not p:
            continue
        if p[0] == "=":
            if len(p) > 1:
                types.append(p[1:])
        else:
            matches.append(p)
    return matches, types

