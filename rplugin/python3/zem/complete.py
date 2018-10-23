import collections
import itertools
import re
from pathlib import Path

def completion_results(matches, cwd):
    res = []
    for m in matches:
        info = None
        try:
            loc = m['location']
            file_name = Path(m['file'])
            if not file_name.is_absolute():
                file_name = cwd/file_name
            with file_name.open("rt") as f:
                if not loc:                                     # Head of File
                    info = "".join(itertools.islice(f,0,5))
                elif loc[0] == '/' == loc[-1]:                  # Line -Regex
                    # loc is a very-no-magic regex where only ^, $, / and \ have meaaning
                    loc = loc[2:-2] # strip /^   $/,
                    loc = loc.replace("\\/","/")
                    loc = loc.replace("\\$","$")
                    loc = loc.replace("\\^","^")
                    loc = loc.replace("\\\\","\\")
                    for info in f:
                        if loc == info[:-1]:
                            break
                    else:
                        info = loc
                    info += "".join(itertools.islice(f,0,4)) # Add 4 lines if there are any left
                else:                                           # Line Number
                    line_no = int(loc)
                    info = "".join(itertools.islice(f, line_no-1, line_no+4))
        except (FileNotFoundError, ValueError):
            pass
        if not info:
            info = f"{m['type']}\n{m['location']}\n{m['extra']}"
        r = {
                'word': m['name'],
                'icase':1,
                'menu': m['file'],
                'info': info
            }
        res.append(r)
    return {"words":res,"refresh":"always"}
