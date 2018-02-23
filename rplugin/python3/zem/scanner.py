import pathlib
import re

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
    exclude = settings.get("exclude", [ "*~", ".git/.", ".svn/", "*.pyc", "*.o", "*.class", ])
    typ     = settings.get("type",    "File")

    root = pathlib.Path(root)
    paths = (p.as_posix() for pattern in pattern for p in root.glob(pattern) )
    if exclude:
        exclude = translate(exclude)
        paths = ( p for p in paths if not exclude.match(p) )
    result = []
    location = None
    for p in paths:
        match = p
        file = p
        result.append((match, typ, file, location))
    return result

def tags(settings):
    tag_files = settings.get("tag_files")
    type_map  = settings.get('type_map')
    if not tag_files:
        tag_files = []
        if pathlib.Path("tags").exists():
            tag_files.append("tags")
        if pathlib.Path(".tags").exists():
            tag_files.append(".tags")
    if not type_map:
        type_map = {
            'd':'Define',
            'p':'Prototyp',
            'x':'Prototyp',         # extern variable
            't':'Typedef',          # typedef name
            'e':'Typedef',          # enum name
            'u':'Typedef',          # union name
            's':'Typedef',          # struct name
            'c':'Typedef',          # class name
            'f':'Implementation',   # function impl
            'v':'Implementation',   # variable
            'l':'Implementation',   # label
            'm':'Implementation',   # member
            'e':'Define',           # enum value
            'F':'File',
        }
    result = []
    for t in tag_files:
        with open(t,"rt") as f:
            for line in f:
                if line.startswith("!"):
                    continue
                parts = line.strip().split("\t")
                match = parts[0]
                file  = parts[1]
                location = parts[2]
                typ = ""
                for field in parts[3:]:
                    if not ':' in field:
                        typ = field
                        typ = type_map.get(typ, typ+'-tagkind')
                result.append((match, typ, file, location))
    return result
