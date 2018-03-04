import pathlib
import re
import subprocess

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

def tags(settings):
    tag_file = settings.get("file")
    type_map  = settings.get('type_map')
    tag_command = settings.get("command")
    if not tag_file:
        if tag_command:
            tag_file = ".tags"
            tag_command += " -f " + tag_file
            p = subprocess.Popen(
                    tag_command,
                    stdin = subprocess.PIPE,
                    stdout = subprocess.PIPE,
                    stderr = subprocess.PIPE,
            )
            print("running "+tag_command)
            out, err = p.communicate()
            if p.returncode != 0:
                raise OSError("Non Zero returncode", p.returncode, tag_command, out, err)
            print(out)
        if pathlib.Path("tags").exists():
            tag_file = "tags"
        elif pathlib.Path(".tags").exists():
            tag_file = ".tags"
        else:
            return []
    else:
        if tag_command is not None:
            raise TypeError("Both command and file defined")

    if not type_map:
        type_map = {
            'd':'Define',
            'p':'Prototyp',
            'x':'Prototyp',         # extern variable
            't':'Type',             # typedef name
            'e':'Type',             # enum name
            'u':'Type',             # union name
            's':'Type',             # struct name
            'c':'Type',             # class name
            'f':'Implementation',   # function impl
            'v':'Implementation',   # variable
            'l':'Implementation',   # label
            'm':'Implementation',   # member
            'e':'Define',           # enum value
            'F':'File',
        }
    result = []

    tag_file = pathlib.Path(tag_file)

    with tag_file.open("rt", errors="replace") as f:
        for line in f:
            if line.startswith("!"):
                continue
            parts = line.strip().split("\t")
            match = parts[0]
            file  = parts[1]
            location = parts[2]
            if location[-2:] == ';"':
                location = location[:-2]
            typ = ""
            for field in parts[3:]:
                if not ':' in field:
                    typ = field
                    typ = type_map.get(typ, typ+'-tagkind')
            result.append((match, typ, file, location))
    print("scanned {} tags from {}".format(len(result),tag_file))
    return result
