import io
import logging
import pathlib
import re
import subprocess
import time

_logger = logging.getLogger(__name__)


def _translate(lines, parent=""):
    """Translate exclude pattenrs like .gitignore to regex."""
    result = []

    if parent:
        assert parent[0] != "/"
        assert parent[-1] != "/"
        parent = re.escape(parent) + "/"

    for l in lines:
        negate = False
        only_dir = False
        l = l.strip()
        if not l:
            continue
        if l[0] == "#":  # comment
            continue
        if l[0] == "!":  # negated
            negate = True
            l = l[1:]

        if l[0] == "\\":
            l = l[1:]

        if l[0] == "/":  # /a/b  -> parent/a/b
            l = l[1:]
        elif l[:1] == "**":  # **/a  -> parent/**/a
            pass
        else:  # a/b   -> parent/**/a/b
            l = "**/" + l

        if l[-1] == "/":  # only match dirs
            l = l[:-1]
            only_dir = True

        r = [parent]
        i = 0
        while i < len(l):
            c = l[i]
            if c == "*":
                s = "[^/]*"
                try:
                    if l[i : i + 3] == "**/":
                        i += 2
                        s = "(?:.*/)?"
                    elif l[i : i + 2] == "**":
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
            yield d
            return
        for f in exclude_files:
            p = d / f
            if p.is_file():
                logger.debug("add {} to excludes", p)
                with p.open("rt") as f:
                    x = _translate(f, d.relative_to(root).as_posix())
                exclude_stack = exclude_stack + x
        for p in d.glob("*"):
            s = p.relative_to(root).as_posix()
            isdir = p.is_dir()
            exclude = False
            for r, d, n in reversed(exclude_stack):
                if d and not isdir:
                    continue
                if r.match(s):
                    if n:  # explicit include
                        break
                    else:
                        exclude = True
                        break
            if not exclude:
                # implicit include
                yield from walk(p, exclude_stack)

    yield from walk(root, excludes)


def files(settings={}):
    """Index the directory Tree."""

    logger = _logger.getChild("files")

    root = settings.get("root", ".")
    typ = settings.get("type", "File")
    subprio = settings.get("subprio", 50)
    prio = settings.get("prio", 99)
    exfiles = settings.get("exclude_files", [".gitignore", ".p4ignore"])
    exclude = settings.get(
        "exclude",
        [
            "*~",
            ".*/",
            "*.pyc",
            "*.o",
            "*._*",
            "*.class",
            "!*.map",
        ],
    )

    root = pathlib.Path(root)

    logger.info("Index files in {}", root.absolute().as_posix())
    t = time.perf_counter()
    files = [
        (f.name, typ, f.as_posix(), None, None, prio, subprio)
        for f in _file_walk(root, exclude, exfiles)
    ]
    t = time.perf_counter() - t
    logger.info("Indexed {} files in {:.3f}s", len(files), t)

    return files


def lines(settings={}):
    """Index lines of files.

    to only search some files, set exclude to '*','!*.c','!*.h' and
    exclude_files to [] if they contain !file patterns"""

    logger = _logger.getChild("lines")

    root = settings.get("root", ".")
    typ = settings.get("type", "UseLine")
    prio = settings.get("prio", 49)
    subprio = settings.get("subprio", 50)
    exfiles = settings.get("exclude_files", [".gitignore", ".p4ignore"])
    limit = settings.get("size_limit", 1 * 1024 * 1024)
    r = settings.get("filter", r"[a-zA-Z_0-9]")
    exclude = settings.get(
        "exclude",
        [
            "*~",
            ".*",
            "*.pyc",
            "*.o",
            "*._*",
            "*.class",
        ],
    )

    root = pathlib.Path(root)

    r = re.compile(r)

    logger.info("Index lines in files in {}", root.absolute().as_posix())
    t = time.perf_counter()
    data = []
    for p in _file_walk(root, exclude, exfiles):
        size = p.stat().st_size
        if size > limit:
            logger.info("File too large: {} {}b", p, size)
            continue
        logger.info("indexing: {}", p)
        with p.open("rt", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if r.search(line):
                    data.append((line, typ, p.as_posix(), None, i + 1, prio, subprio))

    t = time.perf_counter() - t
    logger.info("Indexed {} lines in {:.3f}s", len(data), t)

    return data


def words(settings={}):
    """Index lines of files.

    to only search some files, set exclude to '*','!*.c','!*.h' and
    exclude_files to [] if they contain !file patterns"""

    logger = _logger.getChild("words")

    root = settings.get("root", ".")
    typ = settings.get("type", "UseWord")
    prio = settings.get("prio", 48)
    subprio = settings.get("subprio", 40)
    exfiles = settings.get("exclude_files", [".gitignore", ".p4ignore"])
    limit = settings.get("size_limit", 100 * 1024)
    r = settings.get("re", r"[a-zA-Z_][a-zA-Z_0-9]+")
    exclude = settings.get(
        "exclude",
        [
            "*~",
            ".*",
            "*.pyc",
            "*.o",
            "*._*",
            "*.class",
        ],
    )

    root = pathlib.Path(root)

    r = re.compile(r)

    logger.info("Index words in files in {}", root.absolute().as_posix())
    t = time.perf_counter()
    data = []

    for p in _file_walk(root, exclude, exfiles):
        size = p.stat().st_size
        if size > limit:
            logger.info("File too large: {} {}b", p, size)
            continue
        logger.info("indexing: {}", p)
        with p.open("rt", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                line = line.strip()
                for m in r.finditer(line):
                    data.append(
                        (m.group(0), typ, p.as_posix(), line, i + 1, prio, subprio)
                    )
    t = time.perf_counter() - t
    logger.info("Indexed {} words in {:.3f}", len(data), t)

    return data


# ctags --list-kinds
TAGS_DEFAULT_TYPE_MAP = {
    "h": {
        # k    type          subprio
        "I": ("UseFile", 45),  # include
        "c": ("TypeClass", 90),  # class
        "d": ("Define", 75),
        "e": ("DefEnum", 75),  # enum value
        "g": ("TypeEnum", 75),  # enum name
        "f": ("ImpFunc", 85),  # function  implementation
        "l": ("ImpVarLoc", 60),  # local variable
        "m": ("ImpMember", 80),  # member
        "n": ("NameSpace", 70),
        "p": ("ProtoFunc", 70),  # Function Prototype
        "s": ("TypeStruct", 75),  # struct
        "t": ("TypeDef", 80),  # typedef
        "u": ("TypeUnion", 75),  # union
        "v": ("ImpVar", 85),  # variable
        "x": ("ProtoVar", 70),  # extern    variable
    },
    "c": {
        # k    type          subprio
        "I": ("UseFile", 45),  # include
        "c": ("TypeClass", 90),  # class
        "d": ("Define", 75),
        "e": ("DefEnum", 75),  # enum value
        "g": ("TypeEnum", 75),  # enum name
        "f": ("ImpFunc", 85),  # function  implementation
        "l": ("ImpVarLoc", 60),  # local variable
        "m": ("ImpMember", 80),  # member
        "n": ("NameSpace", 70),
        "p": ("ProtoFunc", 70),  # Function Prototype
        "s": ("TypeStruct", 75),  # struct
        "t": ("TypeDef", 80),  # typedef
        "u": ("TypeUnion", 75),  # union
        "v": ("ImpVar", 85),  # variable
        "x": ("ProtoVar", 70),  # extern    variable
    },
    "py": {
        # k    type          subprio
        "c": ("TypeClass", 90),  # class
        "f": ("ImpFunction", 85),  # function  implementation
        "i": ("UseFile", 45),  # import
        "k": ("ImpFuncLoc", 60),  # local  function  implementation in method
        "m": ("ImpMember", 80),  # member
        "v": ("ImpVar", 85),  # variable
    },
    "s": {
        "d": ("Define", 75),
        "l": ("ImpLabel", 85),
        "m": ("Define", 80),  # macro
        "t": ("TypeDef", 80),  # structs and records
    },
    "asm": {
        "d": ("Define", 75),
        "l": ("ImpLabel", 85),
        "m": ("Define", 80),  # macro
        "t": ("TypeDef", 80),  # structs and records
    },
    "txt": {
        "t": ("Target", 90),
        "v": ("Variable", 50),
        "f": ("Function", 50),
        "D": ("Option", 60)
    },
    "default": {
        # k    type          subprio
        "c": ("TypeClass", 90),  # class
        "f": ("ImpFunction", 85),  # function  implementation
        "v": ("ImpVar", 85),  # variable
        "F": ("File", 50),  # ctags can create a tag for each file
    },
}


def tags(settings={}):
    logger = _logger.getChild("tags")


    tag_file = settings.get("file")
    prio = settings.get("prio", 99)
    type_map = settings.get("type_map", {})
    command = settings.get("command")

    logger.debug("running ctags in %s, tag_file=%s, command=%s, prio=%d", pathlib.Path.cwd().absolute(), tag_file, command, prio)

    if command:
        if tag_file[0] == "!":
            raise ValueError("specifyiing both command and !file", command, tag_file)
        logger.info(f"running {command}")
        t = time.perf_counter()
        p = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        t = time.perf_counter() - t
        if p.wait() == 0:
            logger.info(
                f"ctags took {t:.3f}s " + p.stdout.read() +  p.stderr.read()
            )  # if --totals, print that
        else:
            raise OSError("Non 0 Return Code", p.returncode, p.stderr.read(), command)

    if not tag_file:
        for f in ".tags", "tags":
            if pathlib.Path(f).is_file():
                tag_file = f

    if not tag_file:
        tag_file = "!ctags -o - --recurse --sort=no"

    if tag_file[0] == "!":
        logger.info("running %s", tag_file)
        t = time.perf_counter()
        ctags_process = subprocess.Popen(
            tag_file[1:],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
        )
        f = ctags_process.stdout
        logger.debug("ctags process: %r", ctags_process)
    else:
        ctags_process = None
        logger.info("Parsing %s", tag_file)
        tag_file = pathlib.Path(tag_file)
        f = tag_file.open("rb")

    f = io.TextIOWrapper(f, errors="replace")

    data = []

    t = time.perf_counter() - t
    with f:
        for line in f:
            if line.startswith("!"):
                continue
            l = line.strip()

            name, _, l = l.partition("\t")
            file, _, l = l.partition("\t")
            # location regex could contain tabs
            location, _, l = l.rpartition(';"\t')

            file = file.replace("\\", "/")
            if file.startswith("./"):
                file = file[2:]

            if location.startswith("/"):
                if location[-1] != "/":
                    raise ValueError(
                        "Invalid Tags-location /../ expected", location, line
                    )
            else:
                if not all(c in "0123456789" for c in location):
                    raise ValueError(
                        "Invalid Tags-location (/../ or number expected)",
                        location,
                        line,
                    )

            typ = ""
            extra = ""
            for field in l.split("\t"):
                if ":" not in field:
                    typ = field
                else:
                    k, _, val = field.partition(":")
                    if k == "kind":
                        typ = val
                    elif val:
                        extra = extra + field + " "
            ext = file.rpartition(".")[2]
            ext = ext.rpartition("/")[2]
            try:
                typ, subprio = type_map[ext][typ]
            except KeyError:
                try:
                    typ, subprio = type_map["default"][typ]
                except KeyError:
                    try:
                        typ, subprio = type_map[typ]
                        subprio + 10  # ugly shit: raise TypeError for non int
                        typ + ""  # ugly shit: raise TypeError for non int
                    except (KeyError, ValueError, TypeError):
                        try:
                            typ, subprio = TAGS_DEFAULT_TYPE_MAP[ext][typ]
                        except KeyError:
                            try:
                                typ, subprio = TAGS_DEFAULT_TYPE_MAP["default"][typ]
                            except KeyError:
                                typ, subprio = f"X-{ext}-{typ}", 5
            data.append((name, typ, file, extra, location, prio, subprio))

    count = len(data)
    t = time.perf_counter() - t
    logger.debug(f"Parsed {count} tags in {t:.3f} seconds")

    if ctags_process:
        err = ctags_process.stderr.read().decode(errors="replace")
        if ctags_process.wait(timeout=0.5) != 0: # we already read all of stdout and stderr, wait shouldn't take long
            raise OSError("Non Zero returncode", ctags_process.returncode, tag_file, err)
        if err:
            logger.warn("command printed to stderr: %s", err)
        if not data:
            logger.warn("No Tags from command ", tag_file)

    return data
