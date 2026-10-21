# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scaled Arabic ligature bodies with broken ActualText. Synthetic geometry only."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pymupdf as fitz
from foldertomd import pdf as P


def _scaled_body():
    doc=fitz.open(); page=doc.new_page(width=300,height=150)
    cmap=(b'/CIDInit /ProcSet findresource begin 12 dict begin begincmap '
          b'/CMapName /T def /CMapType 2 def 1 begincodespacerange <00> <FF> '
          b'endcodespacerange 1 beginbfchar <42> <0633> endbfchar '
          b'endcmap CMapName currentdict /CMap defineresource pop end end')
    tu=doc.get_new_xref();doc.update_object(tu,'<<>>');doc.update_stream(tu,cmap,new=True)
    font=doc.get_new_xref()
    doc.update_object(font,f'<</Type/Font/Subtype/Type1/BaseFont/ABCDEF+TestArabic'
                      f'/FirstChar 66/LastChar 66/Widths[995]'
                      f'/Encoding<</Type/Encoding/BaseEncoding/WinAnsiEncoding'
                      f'/Differences[66 /u06330649.f]>>/ToUnicode {tu} 0 R>>')
    doc.xref_set_key(page.xref,'Resources',f'<</Font<</F1 {font} 0 R>>>>')
    stream=(b'BT /F1 1 Tf 23.4 0 0 18 100 110 Tm '
            b'/Span<</ActualText<FEFFFFFD>>> BDC (B) Tj EMC ET')
    content=doc.get_new_xref();doc.update_object(content,'<<>>')
    doc.update_stream(content,stream,new=True)
    doc.xref_set_key(page.xref,'Contents',f'{content} 0 R')
    return doc


def test_replacement_body_uses_trace_horizontal_size():
    doc=_scaled_body();page=doc[0]
    blocks=page.get_text('rawdict')['blocks']
    body=blocks[0]['lines'][0]['spans'][0]['chars'][0]
    assert body['c']=='\ufffd'
    assert P._mark_ligature_bodies(doc,page,blocks,{})
    assert body['lig']=='سى'


def _char(ch,x0,x1,y=110):
    return {'c':ch,'bbox':(x0,y-13,x1,y+3),'origin':(x0,y)}


def test_dot_letters_from_a_separate_line_join_the_body():
    # Dot glyphs carry ش and ي but the body is stored in another PDF line.
    body=_char('\ufffd',100,123.283);body['lig']='سى'
    lines=[{'dir':(1,0),'bbox':(100,97,123.283,113),
            'spans':[{'font':'TestArabic','size':20.52,'bbox':(100,97,123.283,113),'chars':[body]}]},
           {'dir':(1,0),'bbox':(106,92,118,116),
            'spans':[{'font':'TestArabic','size':20.52,'bbox':(106,92,118,116),
                      'chars':[_char('ش',118,118,105),_char('ي',106,106,114)]}]}]
    joined=P._join_split_lines(lines)
    assert len(joined)==1
    assert P._line_text(joined[0],[],False)=='شي'
