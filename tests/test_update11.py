# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update11: decimal marks and choice of extra OCR sample pages (pure functions)."""
import sys, collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from foldertomd.fontdecode import decimal_marks, FontModel

def test_decimal_comma_between_digits():
    assert decimal_marks('السعة ١،٤٤ ميقابايت')=='السعة ١٫٤٤ ميقابايت'
    assert decimal_marks('٠،٥ من نقطة')=='٠٫٥ من نقطة'
    assert decimal_marks('٦٧٣،٣ داين')=='٦٧٣٫٣ داين'

def test_decimal_comma_leaves_ambiguous_and_text_commas():
    assert decimal_marks('٢،١٢٥')=='٢،١٢٥'                 # three digits: could be thousands
    assert decimal_marks('٥٠٠،٠٠٠')=='٥٠٠،٠٠٠'
    assert decimal_marks('الأرضية ، مياه')=='الأرضية ، مياه'
    assert decimal_marks('١، ٢')=='١، ٢'
    assert decimal_marks('سرعته ١٦، ومشغل')=='سرعته ١٦، ومشغل'

class _Doc:
    def __init__(self): self.n=6
    def __getitem__(self,i): return type('P',(),{'rotation':0})()

def test_extra_pages_cover_unknown_glyphs_greedily(monkeypatch):
    import foldertomd.fontdecode as F
    glyphs={0:['a']*20,1:['a']*20+['b']*15,2:['b']*15,3:['c']*3,4:['d']*9,5:[]}
    monkeypatch.setattr(F,'page_glyphs',lambda page,names:[(k,True,None,None,0,'') for k in glyphs[page.n]])
    class Doc:
        def __getitem__(self,i): return type('P',(),{'rotation':0,'n':i})()
    m=FontModel.__new__(FontModel); m.doc=Doc(); m.names={}; m.mapping={}; m.blank=set()
    pick=m.pick_extra_pages(list(range(6)),taken=set(),max_pages=3)
    assert pick==[1,4]                                    # page 1 covers a+b, page 4 adds d; page 3 is below min_gain, page 2 adds nothing new
    assert m.pick_extra_pages(list(range(6)),taken={1},max_pages=3)==[0,2,4]
