# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
import io, posixpath, zipfile
from defusedxml.ElementTree import fromstring
from PIL import Image
from .render import text, table, safe_link, url

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
P='{http://schemas.openxmlformats.org/presentationml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

def relationships(z,part):
    base=posixpath.dirname(part); name=posixpath.basename(part)
    path=base+'/_rels/'+name+'.rels'
    if path not in z.namelist(): return {}
    result={}
    for rel in fromstring(z.read(path)):
        target=rel.get('Target','')
        if rel.get('TargetMode')!='External': target=posixpath.normpath(base+'/'+target) if not target.startswith('/') else target.lstrip('/')
        result[rel.get('Id')]={'target':target,'external':rel.get('TargetMode')=='External','type':rel.get('Type','')}
    return result

def embedded(z,node,rels,ctx,label):
    ids=[]
    for b in node.iter(A+'blip'):
        ident=b.get(R+'embed') or b.get(R+'link')
        if ident: ids.append(ident)
    for b in node.iter('{urn:schemas-microsoft-com:vml}imagedata'):
        if b.get(R+'id'): ids.append(b.get(R+'id'))
    for ident in dict.fromkeys(ids):
        rel=rels.get(ident)
        if not rel or rel['external']:
            ctx.warn(label+': external or unresolved image was not fetched.'); continue
        try:
            data=z.read(rel['target'])
            with Image.open(io.BytesIO(data)) as image: ctx.image(image,label)
        except Exception:
            ctx.warn(label+': image type could not be rendered locally.')

def paragraph(p,rels,ctx):
    def inline(node):
        if node.tag==W+'t': return text(node.text or '')
        if node.tag in (W+'br',W+'cr'): return '  \n'
        if node.tag==W+'tab': return '\t'
        if node.tag==W+'instrText': return '' # field instructions are not visible content
        if node.tag==W+'hyperlink':
            label=''.join(inline(c) for c in node)
            rel=rels.get(node.get(R+'id'))
            if rel and rel['external'] and safe_link(rel['target']): return '['+label+']('+url(rel['target'])+')'
            return label
        if node.tag==W+'txbxContent': return '' # extracted separately
        if node.tag==W+'del': return ''
        return ''.join(inline(c) for c in node)
    value=inline(p).strip()
    style=p.find(f'{W}pPr/{W}pStyle'); style=style.get(W+'val','') if style is not None else ''
    if style.lower().startswith('heading'):
        try: value='#'*min(6,int(style[-1])+1)+' '+value
        except ValueError: value='## '+value
    elif p.find(f'{W}pPr/{W}numPr') is not None: value='- '+value
    return value+'\n\n' if value else ''

def word_nodes(z,root,rels,ctx,label):
    for node in root:
        if node.tag==W+'p':
            ctx.write(paragraph(node,rels,ctx)); embedded(z,node,rels,ctx,label)
            for box in node.iter(W+'txbxContent'):
                ctx.write('### Text box\n\n'); word_nodes(z,box,rels,ctx,label+' text box')
            if any(True for _ in node.iter(W+'object')): ctx.warn(label+': embedded object not executed or extracted.')
        elif node.tag==W+'tbl':
            rows=[]
            for row in node.findall(W+'tr'):
                cells=[]
                for c in row.findall(W+'tc'):
                    cells.append('\n'.join(''.join(t.text or '' for t in p.iter(W+'t')) for p in c.findall(W+'p')))
                    if c.find(f'{W}tcPr/{W}gridSpan') is not None or c.find(f'{W}tcPr/{W}vMerge') is not None:
                        ctx.warn(label+': Word table merges flattened; cell text retained.')
                    embedded(z,c,rels,ctx,label+' table image')
                    if c.find(W+'tbl') is not None: ctx.warn(label+': nested table structure is not preserved.')
                rows.append(cells)
            ctx.write(table(rows))
        elif node.tag in (W+'sdt',W+'sdtContent'):
            word_nodes(z,node,rels,ctx,label)
        elif node.tag==W+'altChunk': ctx.warn(label+': embedded alternate-format content not extracted.')

def extract_word(ctx):
    with zipfile.ZipFile(ctx.source) as z:
        part='word/document.xml'; root=fromstring(z.read(part)); rels=relationships(z,part)
        ctx.stage('Reading document text and images')
        word_nodes(z,root.find(W+'body'),rels,ctx,'Document')
        for name in sorted(z.namelist()):
            if name.startswith('word/') and name.endswith('.xml') and (posixpath.basename(name).startswith(('header','footer')) or name in ('word/footnotes.xml','word/endnotes.xml','word/comments.xml')):
                ctx.write('## '+text(posixpath.basename(name).replace('.xml',''))+'\n\n')
                r=fromstring(z.read(name)); rr=relationships(z,name)
                if 'footnotes' in name or 'endnotes' in name or 'comments' in name:
                    for item in r:
                        if item.get(W+'type') in ('separator','continuationSeparator'): continue
                        ctx.write('Reference '+text(item.get(W+'id',''))+'\n\n'); word_nodes(z,item,rr,ctx,name)
                else: word_nodes(z,r,rr,ctx,name)
        if any('/charts/' in n or '/diagrams/' in n for n in z.namelist()): ctx.warn('Chart/SmartArt objects are not rendered; review original visuals.')
        if any(n.startswith('word/embeddings/') for n in z.namelist()): ctx.warn('Embedded OLE objects are not extracted or executed.')

def slide_shapes(z,root,rels,ctx,label):
    for shape in root:
        if shape.tag==P+'grpSp': slide_shapes(z,shape,rels,ctx,label); continue
        if shape.tag==P+'sp':
            for p in shape.iter(A+'p'):
                val=''.join(t.text or '' for t in p.iter(A+'t'))
                if val:
                    pr=p.find(A+'pPr'); bullet=pr is not None and (pr.find(A+'buChar') is not None or pr.find(A+'buAutoNum') is not None)
                    ctx.write(('- ' if bullet else '')+text(val)+'\n\n')
        elif shape.tag==P+'pic': embedded(z,shape,rels,ctx,label+' image')
        elif shape.tag==P+'graphicFrame':
            tables=list(shape.iter(A+'tbl'))
            for tab in tables:
                rows=[]
                for r in tab.findall(A+'tr'):
                    rows.append(['\n'.join(''.join(t.text or '' for t in p.iter(A+'t')) for p in c.iter(A+'p')) for c in r.findall(A+'tc')])
                ctx.write(table(rows))
            if not tables: ctx.warn(label+': chart, diagram, or embedded object not extracted.')
        elif shape.tag not in (P+'nvGrpSpPr',P+'grpSpPr',P+'cxnSp',P+'extLst'):
            ctx.warn(label+': unsupported shape '+shape.tag.split('}')[-1]+'.')

def extract_powerpoint(ctx):
    with zipfile.ZipFile(ctx.source) as z:
        root=fromstring(z.read('ppt/presentation.xml')); rels=relationships(z,'ppt/presentation.xml')
        slides=root.findall(f'{P}sldIdLst/{P}sldId'); ctx.counts['slides']=len(slides)
        for i,slide in enumerate(slides):
            label=f'Slide {i+1}'; ctx.stage('Reading '+label,i+1,len(slides),'Slide'); ctx.write('## '+label+'\n\n')
            part=rels[slide.get(R+'id')]['target']; rr=relationships(z,part)
            s=fromstring(z.read(part)); tree=s.find(f'{P}cSld/{P}spTree')
            if tree is not None: slide_shapes(z,tree,rr,ctx,label)
            for rel in rr.values():
                if rel['type'].endswith('/notesSlide') and not rel['external']:
                    notes=fromstring(z.read(rel['target'])); ctx.write('### Speaker notes\n\n')
                    for sp in notes.iter(P+'sp'):
                        ph=sp.find(f'{P}nvSpPr/{P}nvPr/{P}ph')
                        if ph is not None and ph.get('type') in ('sldNum','hdr','ftr','dt','sldImg'): continue
                        for p in sp.iter(A+'p'):
                            val=''.join(t.text or '' for t in p.iter(A+'t'))
                            if val: ctx.write(text(val)+'\n\n')
            if s.find(P+'timing') is not None: ctx.warn(label+': animations are not represented in Markdown.')
        if any('/embeddings/' in n for n in z.namelist()): ctx.warn('Embedded OLE objects are not extracted or executed.')
