# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update13: number order around hyphens (bidi) and choice of lines for rare-glyph OCR (pure functions)."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import pymupdf as fitz
from foldertomd.pdf import _visual_line
from foldertomd.fontdecode import FontModel

def spans_from_visual(visual, size=10.0):
    chars=[]; x=10.0
    for ch in visual:
        w=3.0 if ch==' ' else 5.0
        chars.append({'c':ch,'bbox':(x,100.0,x+w,100.0+size)}); x+=w
    return [{'size':size,'bbox':(10.0,100.0,x,100.0+size),'chars':chars}]

def test_year_range_keeps_right_to_left_order():
    # drawn left to right: 2005-2004 then the Arabic word (RTL page); reading order starts with 2004
    visual='٢٠٠٥-٢٠٠٤ '+'ةرتف'+'\ue820'
    assert _visual_line(spans_from_visual(visual))=='فترة ٢٠٠٤-٢٠٠٥'

def test_latin_hyphen_still_joins():
    visual='MC-30 '+'ةجرد'+'\ue820'
    assert _visual_line(spans_from_visual(visual))=='درجة MC-30'

def test_slash_between_arabic_indic_numbers_still_joins():
    visual='٥٧/١٣ '+'رارق'+'\ue820'
    assert _visual_line(spans_from_visual(visual))=='قرار ٥٧/١٣'

def test_unknown_lines_cover_each_code_and_stop(monkeypatch):
    import foldertomd.fontdecode as F
    # page 0: line y=10 has unknown codes a,b ; line y=50 has b ; page 1: line y=10 has c ; page 2 has only known codes
    glyphs={0:[('a',(0,10,5,20),(0,10)),('b',(6,10,11,20),(6,10)),('b',(0,50,5,60),(0,50))],
            1:[('c',(0,10,5,20),(0,10))], 2:[('k',(0,10,5,20),(0,10))]}
    monkeypatch.setattr(F,'page_glyphs',lambda page,names:[(k,True,bb,o,10.0,'') for k,bb,o in glyphs[page.n]])
    class Page:
        rotation=0
        def __init__(self,n): self.n=n; self.rect=fitz.Rect(0,0,200,300)
    class Doc:
        def __getitem__(self,i): return Page(i)
    m=FontModel.__new__(FontModel); m.doc=Doc(); m.names={}; m.mapping={'k':'ك'}; m.blank=set()
    picks=m.pick_unknown_lines([0,1,2],per_code=1,max_lines=10)
    assert [(i,round(r.y0)) for i,r in picks]==[(0,7),(1,7)]     # first line covers a and b, second covers c; line y=50 adds nothing new
    assert len(m.pick_unknown_lines([0,1,2],per_code=2,max_lines=10))==3    # each code up to twice: the y=50 line is now useful
    assert len(m.pick_unknown_lines([0,1,2],per_code=2,max_lines=1))==1     # cap respected
