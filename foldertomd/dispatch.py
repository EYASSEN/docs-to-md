# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
from .context import Context
from .paths import atomic_json

SUPPORTED={'.pdf','.docx','.docm','.doc','.xlsx','.xlsm','.xls','.pptx','.pptm','.ppt','.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp','.txt','.csv','.tsv','.html','.htm','.md'}

def extract(request):
    if request.get('mode')=='count':          # page counts for the overall progress (Update21)
        from .progress import count_request
        count_request(request); return
    from .excel import extract_xlsx,extract_xls
    from .office import extract_word,extract_powerpoint
    from .pdf import extract_pdf
    from .textdocs import extract_text,extract_markdown,extract_image
    from .legacy import extract_legacy
    ctx=Context(request)
    try:
        ext=ctx.source.suffix.lower()
        if ext=='.pdf': extract_pdf(ctx)
        elif ext in ('.xlsx','.xlsm'): extract_xlsx(ctx)
        elif ext=='.xls': extract_xls(ctx)
        elif ext in ('.docx','.docm'): extract_word(ctx)
        elif ext in ('.pptx','.pptm'): extract_powerpoint(ctx)
        elif ext in ('.doc','.ppt'): extract_legacy(ctx)
        elif ext in ('.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp'): extract_image(ctx)
        elif ext=='.md': extract_markdown(ctx)
        else: extract_text(ctx)
        if not ctx.out.closed: ctx.close()
        # A non-Markdown conversion containing only its source comment is suspicious.
        if ext!='.md' and (ctx.work/'result.md').stat().st_size<=len(request['relative'].encode('utf-8'))+25:
            ctx.warn('No document contents were extracted; source may be empty or unsupported.')
        result={'status':'partial' if ctx.warnings else 'converted','warnings':ctx.warnings,'counts':ctx.counts}
    except Exception as e:
        if not ctx.out.closed: ctx.out.close()
        # Avoid logging document/library exception text, which might include formula expressions.
        msg=str(e) if isinstance(e,RuntimeError) else type(e).__name__+': document could not be read; it may be corrupt, protected, inaccessible, or unsupported.'
        result={'status':'failed','warnings':[msg]}
    atomic_json(ctx.work/'response.json',result)
