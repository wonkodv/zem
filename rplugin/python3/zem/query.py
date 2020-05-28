
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

def tokenize(text, *, ignore=('options')):
    query = []
    tts = [tt for tt in TOKEN_TYPES if not tt.attribute in ignore]
    for token in text.split():
        if not token:
            continue
        for tt in tts:
            s = False
            if not tt.key:
                s = token
            else:
                if tt.pos == 'start':
                    if token.startswith(tt.key):
                        if len(token) > len(tt.key):
                            s = token[len(tt.key):]
                        else:
                            break
                elif tt.pos == 'end':
                    if token.endswith(tt.key):
                        if len(token) > len(tt.key):
                            s = token[:-len(tt.key)]
                        else:
                            break
                elif tt.pos == 'in':
                    if tt.key in token:
                        if len(token) > len(tt.key):
                            s = token.replace(tt.key,"",1)
                        else:
                            break
                else:
                    assert False, (token, tt)

            if s:
                query.append((tt, s))
                break
    return query

def tokens_to_string(tokens):
    return " ".join(tt.key+t for (tt,t) in tokens)

