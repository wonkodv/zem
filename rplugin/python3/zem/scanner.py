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

    root = pathlib.Path(root)
    paths = ( (p,p.as_posix()) for pattern in pattern for p in root.glob(pattern) )
    if exclude:
        exclude = translate(exclude)
        paths = ( (p,s) for (p,s) in paths if not exclude.match(s) )
    result = []
    location = None
    for p,s in paths:
        if fullpath:
            match = s
        else:
            match = p.name
        file = s
        result.append((match, typ, file, location))
    print("scanned {} files".format(len(result)))
    return result





TAGS_DEFAULT_TYPE_MAP = {
        'd':'Define',
        'p':'Prototype',
        'x':'ProtoExtern',  #  extern    variable
        't':'TypeDef',      #  typedef   name
        'e':'TypeEnum',     #  enum      name
        'u':'TypeUnion',    #  union     name
        's':'TypStructe',   #  struct    name
        'c':'TypeClass',    #  class     name
        'f':'ImpFunction',  #  function  impl
        'v':'ImpVar',       #  variable
        'l':'ImpLabel',     #  label
        'm':'ImpMember',    #  member
        'e':'DefEnum',      #  enum      value
        'F':'File',
        'I':'UseFile',
        }

def tags(settings):
    tag_file = settings.get("file")
    type_map  = settings.get('type_map')
    tag_command = settings.get("command")
    if tag_command:
        if tag_file:
            raise TypeError("Both command and file defined")
    else:
        if pathlib.Path("tags").exists():
            tag_file = "tags"
        elif pathlib.Path(".tags").exists():
            tag_file = ".tags"
        else:
            return []

    if not type_map:
        type_map = TAGS_DEFAULT_TYPE_MAP

    if tag_command:
            p = subprocess.Popen(
                    tag_command,
                    stdin = subprocess.PIPE,
                    stdout = subprocess.PIPE,
                    stderr = subprocess.PIPE,
            )
            print("running "+tag_command)
            f = p.stdout
    else:
        tag_file = pathlib.Path(tag_file)
        f = tag_file.open("rb")

    f = io.TextIOWrapper(f, errors="replace")

    result = []
    with f:
        for line in f:
            if line.startswith("!"):
                continue
            parts = line.strip().split("\t")
            match = parts[0]
            file  = parts[1]
            location = parts[2]
            if location[-2:] == ';"':
                location = location[:-2]
            location = location.strip()
            typ = ""
            for field in parts[3:]:
                if not ':' in field:
                    typ = field
                    typ = type_map.get(typ, "X-"+typ)
            result.append((match, typ, file, location))

    if tag_command:
        err = p.stderr.read().decode(errors="replace")
        if p.wait(timeout=0.1) != 0:
            raise OSError("Non Zero returncode", p.returncode, tag_command, err)
        print(err)

    print("scanned {} tags from {}".format(len(result),tag_file))
    return result
