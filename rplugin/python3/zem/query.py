
TOKEN_TYPES = {
    'type':  ['=',  'prefix', 'type',   'or'  ],
    'file':  ['/',  'fuzzy',  'file',   'and' ],
    'option':[':',  'ignore', 'option', None  ],
    'extra': ['.',  'fuzzy',  'extra',  'and' ],
    'match': ['',   'fuzzy',  'match',  'and' ],
}

def tokenize(text):
    query = []
    for p in text.split():
        if not p:
            continue
        for typ, (prefix, *_) in TOKEN_TYPES.items():
            l = len(prefix)
            if p.startswith(prefix):
                if len(p) > l:
                    query.append((typ, p[l:]))
                break
    return query

