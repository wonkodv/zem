
TOKEN_TYPES = {
    'type':  ['=',  'prefix', 'type',   'or'  ],
    'file':  ['/',  'fuzzy',  'file',   'and' ],
    'option':['-',  'ignore', 'option', None  ],
    'extra': [':',  'fuzzy',  'extra',  'and' ],
    'name': ['',   'fuzzy',  'name',  'and' ],
}

def tokenize(text, *, ignore=[]):
    query = []
    for p in text.split():
        if not p:
            continue
        for typ, (prefix, *_) in TOKEN_TYPES.items():
            l = len(prefix)
            if p.startswith(prefix):
                if len(p) > l:
                    if typ not in ignore:
                        query.append((typ, p[l:]))
                break
    return query

