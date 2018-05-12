import pathlib
import re
import subprocess
import io

def translate(patterns):
    l = []
    for p in patterns:
        i = 0
        r = []
        while i < len(p):
            c = p[i]
            if c == "*":
                done = False
                try:
                    if p[i:i+3] == "**/":
                        i += 2
                        r.append("(?:.*/)?")
                        done = True
                    elif p[i:i+2] == "**":
                        i += 1
                        r.append(".*")
                        done = True
                except IndexError:
                    pass
                if not done:
                    r.append("[^/]*")
            elif c == "?":
                r.append("[^/]")
            elif c == "/" and i == 0:
                r.append("^")
            elif c == "/" and i == (len(p) - 1):
                r.append("/.*")
            else:
                r.append(re.escape(c))
            i += 1
        r = "".join(r)
        l.append(r)
    r = "|".join(l)
    r = "^(?:.*/)?(?:" + r + ")$"
    r = re.compile(r)
    return r

def files(settings={}):
    """Index the directory Tree."""
    root    = settings.get("root",    ".")
    pattern = settings.get("pattern", ["**/*.*"])
    exclude = settings.get("exclude", [
        "*~",
        ".*/",
        "*.pyc",
        "*.o",
        "*.class",
    ])
    fullpath= settings.get("matchpath", False)
    typ     = settings.get("type",    "File")
    prio    = settings.get("prio",    50)

    root = pathlib.Path(root)
    paths = ( (p,p.as_posix()) for pat in pattern for p in root.glob(pat) )
    if exclude:
        exclude = translate(exclude)
        paths = ( (p,s) for (p,s) in paths if not exclude.match(s) )
    result = []
    location = None
    for p,s in paths:
        if fullpath:
            name = s
        else:
            name = p.name
        file = s
        result.append((name, typ, file, None, location, prio))
    print("scanned {} files".format(len(result)))
    return result

TAGS_DEFAULT_TYPE_MAP = {
        'd':('Define',      75 ),
        'p':('Prototype',   70 ),
        'x':('ProtoExtern', 70 ), #  extern    variable
        't':('TypeDef',     80 ), #  typedef   name
        'e':('TypeEnum',    75 ), #  enum      name
        'u':('TypeUnion',   75 ), #  union     name
        's':('TypStructe',  75 ), #  struct    name
        'c':('TypeClass',   75 ), #  class     name
        'f':('ImpFunction', 80 ), #  function  impl
        'v':('ImpVar',      80 ), #  variable
        'l':('ImpLabel',    85 ), #  label
        'm':('ImpMember',   80 ), #  member
        'e':('DefEnum',     75 ), #  enum      value
        'F':('File',        50 ),
        'I':('UseFile',     45 ),
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
                return []

    types = TAGS_DEFAULT_TYPE_MAP
    if type_map:
        types = types.copy()
        types.update(type_map)

    if tag_command:
            p = subprocess.Popen(
                    tag_command,
                    stdin = subprocess.PIPE,
                    stdout = subprocess.PIPE,
                    stderr = subprocess.PIPE,
            )
            print("running "+tag_command)
            if tag_file:
                err = p.stderr.read().decode(errors="replace")
                if p.wait() != 0:
                    raise OSError("Non Zero returncode", p.returncode, tag_command, err)
            else:
                f = p.stdout
    if tag_file:
        tag_file = pathlib.Path(tag_file)
        f = tag_file.open("rb")

    f = io.TextIOWrapper(f, errors="replace")

    result = []
    with f:
        for line in f:
            if line.startswith("!"):
                continue
            parts = line.strip().split("\t")
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

    if tag_command:
        if not tag_file:
            err = p.stderr.read().decode(errors="replace")
            if p.wait(timeout=0.1) != 0:
                raise OSError("Non Zero returncode", p.returncode, tag_command, err)
            print(err)

    print("scanned {} tags from {}".format(len(result),tag_file))
    return result
