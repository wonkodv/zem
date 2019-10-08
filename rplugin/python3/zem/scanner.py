import pathlib
import re
import subprocess
import io

import logging

_logger = logging.getLogger(__name__)

def _translate(lines, parent=""):
    """Translate exclude pattenrs like .gitignore to regex."""
    result = []

    if parent:
        assert parent[0] != '/'
        assert parent[-1] != '/'
        parent = re.escape(parent) + "/"

    for l in lines:
        negate = False
        only_dir = False
        l = l.strip()
        if not l:
            continue
        if l[0] == '#':         # comment
            continue
        if l[0] == '!':         # negated
            negate = True
            l = l[1:]

        if l[0] == '\\':
            l = l[1:]

        if l[0] == '/':             # /a/b  -> parent/a/b
            l = l[1:]
        elif l[:1] == '**':         # **/a  -> parent/**/a
            pass
        else:                       # a/b   -> parent/**/a/b
            l = '**/'+ l

        if l[-1] == '/':            # only match dirs
            l = l[:-1]
            only_dir = True

        r = [parent]
        i = 0
        while i < len(l):
            c = l[i]
            if c == "*":
                s = "[^/]*"
                try:
                    if l[i:i+3] == "**/":
                        i += 2
                        s = "(?:.*/)?"
                    elif l[i:i+2] == "**":
                        i += 1
                        s = ".*"
                except IndexError:
                    pass
                r.append(s)
            elif c == "?":
                r.append("[^/]")
            else:
                r.append(re.escape(c))
            i += 1
        r = re.compile("".join(r))
        result.append((r, only_dir, negate))

    return result

def _file_walk(root, exclude, exclude_files):
    logger = _logger.getChild("_file_walk")

    root = pathlib.Path(root)

    logger.info("walk {}, exclude {} and from {}", root, exclude, exclude_files)

    excludes = _translate(exclude)

    def walk(d, exclude_stack):
        if d.is_file():
            yield d.relative_to(root)
            return
        for f in exclude_files:
            p = d/f
            if p.is_file():
                logger.debug("add {} to excludes", f)
                with p.open("rt") as f:
                    x = _translate(f, d.relative_to(root).as_posix())
                exclude_stack = exclude_stack + x
        for p in d.glob('*'):
            s = p.relative_to(root).as_posix()
            isdir = p.is_dir()
            exclude = False
            for r,d,n in reversed(exclude_stack):
                if d and not isdir:
                    continue
                if r.match(s):
                    if n:  # explicit include
                        break
                    else:
                        exclude = True
                        break
            if not exclude:
                yield from walk(p, exclude_stack)             # implicit include

    yield from walk(root, excludes)

def files(settings={}):
    """Index the directory Tree."""

    logger = _logger.getChild("files")

    root    = settings.get("root", ".")
    fullpath= settings.get("matchpath", False)
    typ     = settings.get("type",    "File")
    prio    = settings.get("prio",    50)
    exfiles = settings.get("exclude_files", [".gitignore", ".p4ignore"])
    exclude = settings.get("exclude", [
        "*~",
        ".*/",
        "*.pyc",
        "*.o",
        "*._*",
        "*.class",
        "!*.map",
    ])

    root = pathlib.Path(root)

    logger.info("Index files in {}", root.absolute().as_posix())
    for f in _file_walk(root, exclude, exfiles):
        yield (f.name, typ, f.as_posix(), None, None, prio)


def lines(settings):
    """Index lines of files.

    to only search some files, set exclude to '*','!*.c','!*.h' and exclude_files to [] if they
    contain !file patterns"""

    logger = _logger.getChild("lines")

    root    = settings.get("root", ".")
    typ     = settings.get("type",    "UseLine")
    prio    = settings.get("prio",    -10)
    exfiles = settings.get("exclude_files", [".gitignore", ".p4ignore"])
    limit   = settings.get("size_limit", 1*1024*1024)
    r       = settings.get('filter', r'[a-zA-Z_0-9]')
    exclude = settings.get("exclude", [
        "*~",
        ".*",
        "*.pyc",
        "*.o",
        "*._*",
        "*.class",
    ])

    root = pathlib.Path(root)

    logger.debug("Index content of files in {}", root.absolute().as_posix())

    r = re.compile(r)

    for p in _file_walk(root, exclude, exfiles):
        size = p.stat().st_size
        if size > limit:
            logger.info("File too large: {} {}b", p, size)
            continue
        logger.info("indexing: {}", p)
        with p.open("rt") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if r.search(line):
                    yield (line, typ, p.as_posix(), None, i+1, prio)

def words(settings):
    """Index lines of files.

    to only search some files, set exclude to '*','!*.c','!*.h' and exclude_files to [] if they
    contain !file patterns"""

    logger = _logger.getChild("words")

    root    = settings.get("root", ".")
    typ     = settings.get("type",    "UseWord")
    prio    = settings.get("prio",    -10)
    exfiles = settings.get("exclude_files", [".gitignore", ".p4ignore"])
    limit   = settings.get("size_limit", 100*1024)
    r       = settings.get('re', r'[a-zA-Z_][a-zA-Z_0-9]+')
    exclude = settings.get("exclude", [
        "*~",
        ".*",
        "*.pyc",
        "*.o",
        "*._*",
        "*.class",
    ])

    root = pathlib.Path(root)

    logger.debug("Index words of files in {}", root.absolute().as_posix())

    r = re.compile(r)

    for p in _file_walk(root, exclude, exfiles):
        size = p.stat().st_size
        if size > limit:
            logger.info("File too large: {} {}b", p, size)
            continue
        logger.info("indexing: {}", p)
        with p.open("rt") as f:
            for i, line in enumerate(f):
                line = line.strip()
                for m in r.finditer(line):
                    yield (m.group(0), typ, p.as_posix(), line, i+1, prio)

TAGS_DEFAULT_TYPE_MAP = {
        'd':('Define',      75 ),
        'p':('Prototype',   70 ), #  Function Prototype
        'x':('ProtoExtern', 70 ), #  extern    variable
        't':('TypeDef',     80 ), #  typedef
        'e':('TypeEnum',    75 ), #  enum
        'u':('TypeUnion',   75 ), #  union
        's':('TypeStruct',  75 ), #  struct
        'c':('TypeClass',   75 ), #  class
        'f':('ImpFunction', 80 ), #  function  implementation
        'v':('ImpVar',      80 ), #  variable
        'l':('ImpLabel',    85 ), #  label
        'm':('ImpMember',   80 ), #  member
        'e':('DefEnum',     75 ), #  enum      value
        'F':('File',        50 ),
        'I':('UseFile',     45 ), #  include
        }

def tags(settings):
    logger = _logger.getChild("tags")

    logger.debug("running in %s", pathlib.Path.cwd().absolute())

    tag_file = settings.get("file")
    type_map  = settings.get('type_map')

    types = TAGS_DEFAULT_TYPE_MAP
    if type_map:

        types = types.copy()
        types.update(type_map)

    if tag_file[0] == '!':
        logger.info("running %s", tag_file)
        p = subprocess.Popen(
                tag_file[1:],
                stdin = subprocess.PIPE,
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
                shell=True,
        )
        f = p.stdout
    else:
        p = None
        logger.info("Parsing %s", tag_file)
        tag_file = pathlib.Path(tag_file)
        f = tag_file.open("rb")

    f = io.TextIOWrapper(f, errors="replace")

    count = 0
    result = []
    with f:
        for line in f:
            if line.startswith("!"):
                continue
            parts = line.strip().split("\t")
            if not len(parts) >= 3:
                raise ValueError("Invalid Tags-Line", line)
            name = parts[0]
            file  = parts[1].replace("\\","/")
            if file.startswith('./'):
                file = file[2:]
            location = parts[2]
            if location[-2:] == ';"':
                location = location[:-2]
            location = location.strip()
            typ = ""
            extra = ""
            for field in parts[3:]:
                if not ':' in field:
                    typ = field
                else:
                    t, _, val = field.partition(":")
                    if t == 'kind':
                        typ = val
                    elif val:
                        extra = extra + field + " "
            if typ:
                typ, prio = types.get(typ, ("X-"+typ, 0))
            yield (name, typ, file, extra, location, prio)
            count += 1;

    logger.debug("Parsed %d records", count)

    if p:
        err = p.stderr.read().decode(errors="replace")
        if p.wait(timeout=0.5) != 0:
            raise OSError("Non Zero returncode", p.returncode, tag_file, err)
        if err:
            logger.warn("command printed to stderr: %s", err)
        if not count:
            logger.warn("No Tags from command ", tag_file)
