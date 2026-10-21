# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
import csv, io, re
from pathlib import Path
from urllib.parse import unquote, urlparse
from charset_normalizer import from_bytes
from bs4 import BeautifulSoup
from markdownify import markdownify
from PIL import Image, ImageSequence
from .render import table, text, safe_link
from .arabicfix import fix_text, looks_cp1256

def decode(data,ctx):
    for enc in ('utf-8-sig','utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8'):
        try: return fix_text(data.decode(enc))
        except UnicodeError: pass
    arabic=looks_cp1256(data)   # old Arabic Windows files; short ones are often mistaken for other code pages
    if arabic is not None:
        ctx.warn('Text encoding inferred as Windows-1256 (Arabic); review non-ASCII characters.')
        return fix_text(arabic)
    match=from_bytes(data).best()
    if match is None: raise RuntimeError('Text encoding could not be determined.')
    ctx.warn('Text encoding inferred as '+match.encoding+'; review non-ASCII characters.')
    return fix_text(str(match))

def extract_text(ctx):
    suffix=ctx.source.suffix.lower()
    content=decode(ctx.source.read_bytes(),ctx)
    if suffix in ('.csv','.tsv'):
        reader=csv.reader(io.StringIO(content),delimiter='\t' if suffix=='.tsv' else ',')
        block=[]; total=0
        for row in reader:
            block.append(row); total+=1
            if len(block)>=200:
                ctx.write(table(block)); block=[]
        if block: ctx.write(table(block))
        ctx.counts['rows']=total
    elif suffix in ('.html','.htm'):
        soup=BeautifulSoup(content,'html.parser')
        for tag in soup(['script','style','iframe','object','embed','form','meta','link','base']): tag.decompose()
        for tag in soup.find_all(True):
            for key in list(tag.attrs):
                if key not in ('href','src','alt','colspan','rowspan'): del tag.attrs[key]
            if tag.name=='a' and not safe_link(tag.get('href','')): tag.attrs.pop('href',None)
            if tag.name=='img':
                src=tag.get('src','')
                local=(Path(ctx.request.get('original_dir',ctx.source.parent))/unquote(src)).resolve()   # images next to the original file (Update14)
                source_root=Path(ctx.request['source_root']).resolve()
                if not urlparse(src).scheme and local.is_relative_to(source_root) and local.is_file():
                    try:
                        with Image.open(local) as image:
                            stream=io.BytesIO(); image.convert('RGB').save(stream,'PNG'); tag['src']=ctx.asset(stream.getvalue())
                    except Exception: tag.decompose(); ctx.warn('An HTML image could not be preserved.')
                else: tag.decompose(); ctx.warn('External or missing HTML image was not fetched.')
        ctx.write(markdownify(str(soup),heading_style='ATX'))
    else:
        # Fence prevents active HTML in plain text, while preserving actual text exactly inside.
        fence='`' * max(3,max((len(m.group(0))+1 for m in re.finditer(r'`+',content)),default=3))
        ctx.write(fence+'text\n'+content+('\n' if not content.endswith('\n') else '')+fence+'\n')

def extract_markdown(ctx):
    ctx.out.close()
    data=ctx.source.read_bytes()
    (ctx.work/'result.md').write_bytes(data)
    # Original Markdown must be byte-identical. Dependencies are inventoried; no rewritten links.
    content=decode(data,ctx)
    dependencies=re.findall(r'!?\[[^\]]*\]\(([^\s)]+)',content)
    if dependencies:
        ctx.warn('Existing Markdown copied without alteration. Local/remote resource dependencies are not copied automatically; check original relative links.')
        ctx.counts['markdown_link_dependencies']=dependencies

def extract_image(ctx):
    with Image.open(ctx.source) as image:
        frames=getattr(image,'n_frames',1); ctx.counts['frames']=frames
        for i,frame in enumerate(ImageSequence.Iterator(image)):
            ctx.stage(f'Reading image frame {i+1} of {frames}',i+1,frames,'Frame')
            ctx.write(f'## Image frame {i+1}\n\n'); ctx.image(frame.copy(),f'Frame {i+1}')
            ctx.complete_unit()
