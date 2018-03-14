import neovim
import re
import pathlib
import time
import os
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
    SPECIAL_KEYS = {
            "<up>"  :"up",
            "<down>":"down",
            "<c-u>" :"update",
            "<cr>"  :":edit {command} {file}",
            "<tab>" :":tabedit {command} {file}",
            "<c-p>" :":pedit {command} {file}",
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
        self.set_buffer_lines(lines)

    def setting(self, key, default):
        return self.nvim.vars.get("zem_{}".format(key), default)

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

    @neovim.command("ZemUpdateIndex", sync=True)
    def zem_update_index(self, *args):
        """Fill the database."""
        t = time.perf_counter()
        l = self.update_index()
        t = time.perf_counter() - t
        self.nvim.out_write("echomsg 'Scanned {} elements in {:.3f} seconds'\n".format(l,t))

    @neovim.command("ZemEdit", nargs="1", sync=True)
    def zem_edit(self, args):
        m = self.get_db().get(*tokenize(" ".join(args)), limit=1)
        if m:
            self.action_with_match(":edit {command} {file}", m[0])

    @neovim.command("ZemTabEdit", nargs="1", sync=True)
    def zem_edit_tab(self, args):
        m = self.get_db().get(*tokenize(" ".join(args)), limit=1)
        if m:
            self.action_with_match(":tabedit {command} {file}", m[0])

    @neovim.command("ZemPreviewEdit", nargs="1", sync=True)
    def zem_edit_prev(self, args):
        m = self.get_db().get(*tokenize(" ".join(args)), limit=1)
        if m:
            self.action_with_match(":pedit {command} {file}", m[0])

    @neovim.command("Zem", nargs="?", sync=True)
    def zem_prompt(self, args):
        """Open the ZEM> Prompt."""
        self.candidates = []
        self._last_tokens = None
        self.count = self.setting("height", 20)
        default_text = " ".join(args)

        self.nvim.command("wincmd n")
        self.buffer = self.nvim.current.buffer
        self.buffer.name = "ZEM"
        self.nvim.command("setlocal filetype=zem_preview")
        self.nvim.command("setlocal winminheight=1")
        self.nvim.command("setlocal buftype=nofile")
        self.nvim.command("setlocal bufhidden=delete")
        self.nvim.command("setlocal noswapfile")
        self.nvim.command("setlocal nobuflisted")
        self.nvim.command("setlocal nowrap")
        self.nvim.command("setlocal nonumber")
        self.nvim.command("setlocal nolist")
        self.nvim.command("wincmd J")
        self.nvim.command("redraw")
        for k in self.SPECIAL_KEYS:
            self.nvim.command("cnoremap <buffer> {} {}".format(k,k.replace("<","<LT>"))) # Special keys just add a <key> sequence
        if not default_text:
            self.set_buffer_lines_with_usage([])

        self.nvim.funcs.inputsave()
        try:
            self.nvim.funcs.input({
                'prompt':self.setting("prompt",'ZEM> '),
                'highlight':'ZemOnKey',
                'default': default_text,
            })
        except KeyboardInterrupt:
            pass
        finally:
            self.nvim.funcs.inputrestore()
        self.close_window()


    @neovim.function("ZemOnKey",sync=True)
    def zem_on_key(self, args):
        """This is the `highlight` argument of `input()` and is called on every key.

        args is `[ inputText ]`

        return a list of highlight options for the input string
        """
        text, = args
        self.nvim.async_call(self.process, text)
        return []

    def close_window(self):
        """Try closing the ZEM Window."""
        if self.buffer:
            self.nvim.command("{}bd".format(self.buffer.number))
            self.buffer = None

    def process(self, text):
        """Update the list of matches and process Special Keys.

        called asyncronously with the current content of the ZEM Prompt

        Special keys are handled by a mapping in the prompt that inserts
        <key> when a special key is pressed.
        This function performs the action for the key and sends key-strokes to
        remove the sequence.

        If the prompt does not contain a special-key-sequence, is not empty or
        invalid (a single `=`), the db is queried for matches and they are
        inserted into the Preview Window.

        The latest result set is cached in `self.candidates`. <UP> and <DOWN> change
        the selected line in the preview window, <TAB> or <CR> use the line
        number to select the candidate and open its file.
        """
        try:
            if '<' in text:
                if '>' in text:
                    for key, action in self.SPECIAL_KEYS.items():
                        if key in text:
                            if self.action(action):
                                self.nvim.input("<BS>"*(len(key))) # remove <key>
                            break
                    else:
                        raise ValueError("unknown special key", text)
                else:
                    pass #start of <key sequence
            else:
                self.update_preview(text)
        except:
            self.on_error()

    def update_preview(self, text):
        """Updatet the matches in the preview window."""
        t = tokenize(text)
        if t == self._last_tokens:  # only query the db if anything changed
            return
        self._last_tokens = t
        if not any(t):
            self.set_buffer_lines_with_usage(["== Nothing to Display ==", "Enter a Query"])
            return
        matches, types = t
        if not types:
            types = self.setting("default_types",[])
        results = self.get_db().get(matches, types, limit=self.count)
        results = list(reversed(results))
        self.candidates = results
        if not results:
            self.set_buffer_lines([
                "== No Matches ==",
                "Maybe update the Database with <C-U>?",
                "words: {}".format(matches),
                "types: {}".format(types)]
            )
        else:
            markup = self.setting("markup","{match:30s}\t{type:15}\t{file}:{location}")
            self.set_buffer_lines([ markup.format(**r) for r in results])

    def action(self, action):
        """Perform the action caused by special keys.

        Returns True if the ZEM Prompt is still open"""
        if action == 'up':
            self.nvim.command("normal k")
            self.nvim.command("redraw")
        elif action == 'down':
            self.nvim.command("normal j")
            self.nvim.command("redraw")
        elif action == 'update':
            self.set_buffer_lines(["Updating..."])
            t = time.perf_counter()
            l = self.update_index()
            t = time.perf_counter() - t
            self.set_buffer_lines(["Scanned {} elements in {:.3f} seconds".format(l,t)])
            self._last_tokens = None # allow update after the BS are sent
        elif action[0] == ":":
            line = self.nvim.funcs.line('.')
            idx = line - 1
            try:
                m = self.candidates[idx]
            except (AttributeError, IndexError):
                self.set_buffer_lines(["No match"])
                return
            self.close_window()                 # destroy the zem window
            self.nvim.input("<ESC>")            # finish the input() prompt
            self.action_with_match(action, m)
            return False
        else:
            raise ValueError("unknown action",action,key,text)
        return True

    def action_with_match(self, action, match):
        assert action[0] == ':'
        action = action[1:]
        l = match['location']
        if l:
            if l[-1] == l[0] == '/':
                l = l[1:-1]
                l = r"/\M{}/".format(l) # use  nomagic mode, where only ^ $ / and \ are special
                l = l.replace(match['match'],"\\zs"+match['match']) # search for identifier, nt start of line (not supported by nvim yet)
                l = l.replace("\\","\\\\").replace(" ","\\ ") # replace space, double no of escapes
            l = "+" + l
        else:
            l = ""
        cmd = action.format(command=l, file=match['file'])
        self.nvim.vars['zem_match'] = dict(match)
        try:
            self.nvim.command(cmd)
            self.nvim.command("nohlsearch|redraw")
        except neovim.api.nvim.NvimError:
            pass # something like ATTENTION, swapfile or so..

    def set_buffer_lines(self, lines):
        self.buffer[:] = lines
        self.nvim.command("{}wincmd _".format(len(lines)))
        self.nvim.command("normal G")   # select first result
        self.nvim.command("redraw")

    def set_buffer_lines_with_usage(self, lines):
        lines = USAGE.format(VERSION, self.get_db().location).split("\n")+[""] + lines
        self.set_buffer_lines(lines)

    def update_index(self):
        os.chdir(self.nvim.funcs.getcwd()) # switch to cwd of active buffer/tab, so relative paths are correct
        data=[]
        for source, param in self.setting("sources", [['files',{}],['tags',{}]]):
            base_param = self.setting("source_{}".format(source), {}).copy()
            base_param.update(param)

            func = getattr(scanner, source, None)
            if func:
                data += func(base_param)
            else:
                data += self.nvim.call(source, param)

        self.get_db().fill(data)
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

