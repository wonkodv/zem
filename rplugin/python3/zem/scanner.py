import pathlib
import re
import subprocess
import io

def translate(lines, parent=""):
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

def files(settings={}):
    """Index the directory Tree."""
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
        "*.class",
        "!*.map",
    ])

    excludes = translate(exclude)
    result = []

    count = 0

    root = pathlib.Path(root)
    def walk(d, exclude_stack):
        nonlocal count
        count += 1
        if d.is_file():
            rp = d.as_posix()
            if fullpath:
                name = rp
            else:
                name = d.name
            result.append((name, typ, rp, None, None, prio))
            return
        for f in exfiles:
            p = d/f
            if p.is_file():
                with p.open("rt") as f:
                    x = translate(f,d.relative_to(root).as_posix())
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
                walk(p, exclude_stack)             # implicit include

    walk(root, excludes)

    print("scanned {} locations, found {} files".format(count, len(result)))
    return result

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
    tag_file = settings.get("file")
    type_map  = settings.get('type_map')
    tag_command = settings.get("command")
    if not tag_command:
        if not tag_file:
            if pathlib.Path("tags").exists():
                tag_file = "tags"
            elif pathlib.Path(".tags").exists():
                tag_file = ".tags"
            else:
                raise ValueError("`tag_command`/`tag_file` setting `.tags` or `tags` file needed")

    types = TAGS_DEFAULT_TYPE_MAP
    if type_map:
        types = types.copy()
        types.update(type_map)

    if tag_command:
            print("running ",tag_command)
            p = subprocess.Popen(
                    tag_command,
                    stdin = subprocess.PIPE,
                    stdout = subprocess.PIPE,
                    stderr = subprocess.PIPE,
            )
            if tag_file:
                err = p.stderr.read().decode(errors="replace")
                if p.wait() != 0:
                    raise OSError("Non Zero returncode", p.returncode, tag_command, err)
            else:
                f = p.stdout
                use_stdout = True

    if tag_file:
        tag_file = pathlib.Path(tag_file)
        f = tag_file.open("rb")
        use_stdout = False

    f = io.TextIOWrapper(f, errors="replace")

    result = []
    with f:
        for line in f:
            if line.startswith("!"):
                continue
            parts = line.strip().split("\t")
            if not len(parts) >= 3:
                raise ValueError("Invalid Tags-Line", line)
            name = parts[0]
            file  = parts[1]
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
            result.append((name, typ, file, extra, location, prio))

    if use_stdout:
        err = p.stderr.read().decode(errors="replace")
        if p.wait(timeout=0.5) != 0:
            raise OSError("Non Zero returncode", p.returncode, tag_command, err)
        if err:
            print(err)
        print("scanned {} tags from {}".format(len(result), tag_command))
        if not result:
            print("does command send to stdout?")
    else:
        print("scanned {} tags from {}".format(len(result), tag_file))

    return result
