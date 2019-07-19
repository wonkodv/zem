
import collections

TokenTyp = collections.namedtuple('TokenTyp',' prefix matchtyp attribute grouping ')

TOKEN_TYPES = (
    TokenTyp('=', 'prefix', 'type',   'or'),
    TokenTyp('/', 'fuzzy',  'file',   'and'),
    TokenTyp('-', 'ignore', 'option', None),
    TokenTyp(':', 'fuzzy',  'extra',  'and'),
    TokenTyp('!', 'exact', 'name',   'and'),
    TokenTyp('',  'fuzzy',  'name',   'and'),
)

def tokenize(text, *, ignore=[]):
    query = []
    for p in text.split():
        if not p:
            continue
        for tt in TOKEN_TYPES:
            l = len(tt.prefix)
            if p.startswith(tt.prefix):
                if len(p) > l:
                    if tt not in ignore:
                        query.append((tt, p[l:]))
                break
    return query

