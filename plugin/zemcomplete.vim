
function! ZemComplete(findstart, base)
    if a:findstart
        let s:completeopt=&completeopt
        augroup zemcomplete
            autocmd!
            au CompleteDone * let &completeopt=s:completeopt | augroup zemcomplete | autocmd! | augroup END
        augroup END

        try
            set completeopt-=longest
            set completeopt+=noinsert
        catch
        endtry
        let line = getline('.')
        let start = col('.') - 1
        while start > 0 && line[start - 1] =~ '[a-zA-Z0-9_/.:=-]'
            let start -= 1
        endwhile
        return start
    else
        let res = []
        let query = substitute(a:base,'_',' ','g')
        return ZemGetCompletions(query, 30)
    endif
endfunction


" set completefunc=ZemComplete

