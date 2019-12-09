
import collections

TokenTyp = collections.namedtuple('TokenTyp','pos key matchtyp attribute grouping ')

TOKEN_TYPES = (
    TokenTyp('start', '=', 'prefix', 'type',   'or'),
    TokenTyp('in', '/', 'fuzzy',  'file',   'and'),
    TokenTyp('start', '-', 'ignore', 'option', None),
    TokenTyp('start', ':', 'fuzzy',  'extra',  'and'),
    TokenTyp('in', '!', 'exact', 'name',   'and'),
    TokenTyp('', '',  'fuzzy',  'name',   'and'),
)

def tokenize(text, *, ignore=[]):
    query = []
    tts = [tt for tt in TOKEN_TYPES if not tt in ignore]
    for token in text.split():
        if not token:
            continue
        for tt in tts:
            s = False
            if not tt.key:
                s = token
            elif len(token) > len(tt.key):
                if tt.pos == 'start':
                    if token.startswith(tt.key):
                        s = token[len(tt.key):]
                elif tt.pos == 'end':
                    if token.endswith(tt.key):
                        s = token[:-len(tt.key)]
                elif tt.pos == 'in':
                    if tt.key in token:
                        s = token.replace(tt.key,"",1)
                else:
                    assert False, (token, tt)

            if s:
                query.append((tt, s))
                break
    return query
