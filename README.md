ZEM
===

Neovim plugin that can quickly navigate to previously indexed locations.

Early development, but useable.

It uses the python3 remote plugin api and sqlite.

You can use `:Zem` to open a prompt with preview window that shows the currently matching
elements, or you can use `:ZemEdit QUERY` to directly go to the location.

Install
-------

1.  put the `zem` folder inside a `rplugin/python3` folder that nvim searches.
    (for example using vim-plug `Plug 'wonkodv/zem'`)

2.  in nvim: `:UpdateRemotePlugins` and restart

3.  (optionaly) define mappings in `init.vim`

        nnoremap <S-Y> :Zem<CR>
        nnoremap <C-y> :Zem<C-R><C-W><CR>
        nnoremap <C-]> :ZemEdit =Impl <C-R><C-W><CR>

Indexing
--------

Before using the `:Zem` command, the Index must be filled. By executing
`:ZemUpdateIndex`, all configured sources are indexed and the elements stored in
an sqlite3 database.

Elements
------

Each element consists of these fields:

*   match:  Text that is matched against to find it (e.g. function name)
*   type:   what this element represents, (e.g. File, Define, ...)
*   file:   which file the element is in
*   location:   how to find the element in the file (Line number or `/{pattern}/`)

Query
-----

Each letter of a word must match in order, but words can match out of order:

        query   | matches     |  doesn't match
    ------------|-------------|-----------------
     fob        |  FooBar     |  Foo 
     ba foo     |  FooBar     |  Foo 
     foofoo     |  FooBarFoo  |  Foo 
     foo foo    |  Foo        |  Bar 

Tokens that start with `=` match against types. If none are given, all types are matched,
otherwise only those types that start with the given ones are matched

        query  | matches
    -----------|-------------
    =I         | ['Implementation', 'Import'] 
    =Impl      | ['Implementation'] 
    =Impl =De  | ['Implementation', 'Define'] 

Matching multiple types might be useful to define mappings that open zem and
narrow down the number of matched types (e.g. `nmap <S-T> :Zem =Define =Type <CR>`)

Sources
-------

The two implemented sources are:

*   `files`:  index files
*   `tags`:   scan a file generated by `ctags` and index each tag.

Config
------

the following configuration variables can be set in `init.vim` and/or, in a
`.nvimrc` file inside each project. (`.nvimrc` files are sourced in the CWD if
the option `exrc` is set.)

*   `g:zem_db`  (`'.zem.sqlite'`) Name of the index database.
*   `g:zem_height`  (`20`) Number of rows in the preview window
*   `g:zem_prompt`  (`'ZEM> '`) Prompt
*   `g:zem_markup`  (...) `python str.format()`-string to display `match`,
                    `typ`, `file`, `location`
*   `g:zem_sources` (`['files', 'tags']`) names of scanners to use. must be implemented in `zem/scanner.py` or vim functions
                    that return elements as `(match, typ, file, location)`-tuples.
*   `g:zem_source_FUNCNAME` Parameter that is passed to the scanner. Can be omitted to use defaults.
    *   `g:zem_source_files` dictionary with these fields:
        *   `root` (`"."`) where to search for files
        *   `pattern` (`["**/*.*"]`) search pattern (python `pathlib.Path.glob()` syntax)
        *   `exclude` (`["*~",".git.","*.pyc",...]`) files to exclude (unusual syntax)
        *   `type`    (`"File"`) type of the matches
    *   `g:zem_source_tags` dictionary with these fields:
        *   `files`   (`['.tags', 'tags']`) files to scan
        *   `type_map` (`{'d':'Define','f':'Implementation', ...}`) Map the tag-kind to Element-type.
            The default maps most tag kinds onto one of: `Define`, `Prototyp`, `Typedef`, `Implementation`

