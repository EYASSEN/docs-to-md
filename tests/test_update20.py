# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update20: Arabic ligature bodies (½ Ë Ñ ... in InDesign/Adobe PDFs) and the lam-alef ligature.
Every PDF here is built by the test itself; character boxes are measured geometry, no document content."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import pymupdf as fitz
from foldertomd import pdf as P


def span(chars,size=13,font='F'):
    """chars: (text, x0, x1[, lig skeleton]) listed in stored order."""
    out=[]
    for ch in chars:
        c={'c':ch[0],'bbox':(ch[1],100,ch[2],112),'origin':(ch[1],110)}
        if len(ch)>3: c['lig']=ch[3]
        out.append(c)
    return [{'size':size,'font':font,'bbox':(0,100,600,112),'chars':out}]


def body_pdf(dots):
    """One word drawn like InDesign does: a dotless tooth+reh body (code B, ToUnicode FFFD, glyph name
    u06490631.f), zero-width dot glyphs carrying letters (codes C, D), then feh (code A) to its left."""
    doc=fitz.open(); page=doc.new_page(width=300,height=100)
    entries=['<41> <0641>','<42> <FFFD>']+[f'<{0x43+i:02X}> <{ord(ch):04X}>' for i,ch in enumerate(dots)]
    cmap=('/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /T def /CMapType 2 def\n'
          '1 begincodespacerange <00> <FF> endcodespacerange\n'
          f'{len(entries)} beginbfchar\n'+'\n'.join(entries)+'\nendbfchar\nendcmap CMapName currentdict /CMap defineresource pop end end')
    tu=doc.get_new_xref(); doc.update_object(tu,'<<>>'); doc.update_stream(tu,cmap.encode(),new=True)
    widths=' '.join(['500','690']+['0']*len(dots))
    names=' '.join(['/uni0641.i','/u06490631.f']+['/arDotAboveCCMP']*len(dots))
    font=doc.get_new_xref()
    doc.update_object(font,f'<</Type/Font/Subtype/Type1/BaseFont/ABCDEF+TestArabic/FirstChar 65/LastChar {66+len(dots)}'
                      f'/Widths[{widths}]/Encoding<</Type/Encoding/BaseEncoding/WinAnsiEncoding/Differences[65 {names}]>>/ToUnicode {tu} 0 R>>')
    doc.xref_set_key(page.xref,'Resources','<</Font<</F1 %d 0 R>>>>'%font)
    ops=['BT /F1 10 Tf 1 0 0 1 100 50 Tm (B) Tj']
    for i,x in enumerate((105,102.5)[:len(dots)]): ops.append(f'1 0 0 1 {x} 53 Tm ({chr(0x43+i)}) Tj')
    ops.append('1 0 0 1 95 50 Tm (A) Tj ET')
    cx=doc.get_new_xref(); doc.update_object(cx,'<<>>'); doc.update_stream(cx,' '.join(ops).encode(),new=True)
    doc.xref_set_key(page.xref,'Contents','%d 0 R'%cx)
    return doc


def page_text(doc):
    page=doc[0]; blocks=page.get_text('rawdict',sort=True)['blocks']
    P._mark_ligature_bodies(doc,page,blocks,{})
    return '\n'.join('\n'.join(P._line_text(l,[],False) for l in P._join_split_lines(b['lines'])) for b in blocks if b['type']==0)


def test_body_glyph_is_replaced_by_its_letters():
    # body + dots ن ز reads نزف; the raw code character (B) never reaches the output
    assert page_text(body_pdf('نز'))=='نزف'


def test_letter_without_dots_is_recovered_from_the_glyph_name():
    # the same body with only a ت dot is تر: the reh has no dot glyph, its name says it is there
    assert page_text(body_pdf('ت'))=='ترف'


def test_skeleton_names():
    assert P._skeleton('u06490631.f')=='\u0649\u0631'
    assert P._skeleton('u06A10649')=='\u06a1\u0649'
    assert P._skeleton('uni0646.i')=='\u0646'
    assert P._skeleton('arDotAboveCCMP') is None and P._skeleton('A') is None and P._skeleton('u0041') is None


def test_fill_ligature_families():
    assert P._fill_ligature('\u06a1\u0649',['ف','ي'])==('في',2)        # في
    assert P._fill_ligature('\u0649\u06ba',['ي','ن'])==('ين',2)        # بين
    assert P._fill_ligature('\u0649\u0631',['ت'])==('تر',1)            # فترات
    assert P._fill_ligature('\u0649\u0631',['ي','ز'])==('يز',2)        # تركيز
    assert P._fill_ligature('\u0649\u0649',['ت'])==('تى',1)            # حتى
    assert P._fill_ligature('',['ش'])==('ش',1)                          # unknown body: its dots only


def test_body_with_bogus_space_between_its_dots():
    # بين: ب, body (ى+ں) with zero-width ي and ن and a "space" between them inside the body
    out=P._visual_line(span([('ب',233.3,236.0),('Ñ',224.9,233.3,'\u0649\u06ba'),('ي',231.9,231.9),(' ',227.6,231.9),('ن',227.6,227.6),(' ',222.4,224.9),('ا',219.9,222.4)]))
    assert out=='بين ا'


def test_diacritics_on_a_body_follow_their_letter():
    # تبيِّن: kasra and shadda sit by the ي dots, not at the end of the body
    out=P._visual_line(span([('ت',221.0,225.0),('ب',216.8,221.0),('Ý',204.6,216.8,'\u0649\u06ba'),('ي',214.7,214.7),
                              ('\u0650',213.3,213.3),('\u0651',213.3,213.3),(' ',208.3,213.3),('ن',208.3,208.3)]))
    assert out.replace('\u0650\u0651','\u0651\u0650')=='تبي\u0651\u0650ن'


def test_hamza_alef_inside_lam_alef_belongs_to_the_lam():
    # الأيام: zero-width أ inside the lam-alef glyph, touching the right edge of the ي
    out=P._visual_line(span([('ا',285.7,288.0),('ل',279.9,285.7),('أ',280.3,280.3),('ي',277.5,280.2),('ا',275.1,277.5),('م',268.0,275.1)]))
    assert out=='الأيام'
    # والآخر
    out=P._visual_line(span([('و',191.8,196.5),('ا',190.4,192.7),('ل',184.6,190.3),('آ',184.9,184.9),('خ',179.5,185.5),('ر',175.1,179.5)]))
    assert out=='والآخر'


def test_alef_on_the_edge_between_two_lams():
    # اللاجئ: the alef sits exactly on the edge of the first lam and of the lam-alef glyph
    out=P._visual_line(span([('ا',505.0,507.1),('ل',502.5,504.9),('ا',502.5,502.5),('ل',496.9,502.5),('ج',492.2,497.8),('ئ',489.5,492.2)]))
    assert out=='اللاجئ'


def test_unknown_replacement_glyph_is_kept_without_dots():
    out=P._visual_line(span([('ب',110,114),('\ufffd',100,110),('ا',96,100)]))
    assert '\ufffd' in out


def test_replacement_glyph_with_dots_is_a_body():
    out=P._visual_line(span([('ن',139.2,143.2),('خ',130.1,139.2),('\ufffd',112.2,130.1),('ش',124.9,124.9)]))
    assert out=='نخش'


def test_body_resolved_by_width():
    wide=[(995.0,'\u0633\u0649'),(844.0,'\u0633\u0631'),(539.0,'\u0649\u0631')]
    assert P._by_width(wide,994.5)=='\u0633\u0649'
    assert P._by_width(wide,700) is None
    assert P._by_width([(500.0,'a'),(502.0,'b')],501) is None           # ambiguous


def test_rotated_line_uses_stored_order():
    # a slanted heading: positions cannot order it, the body comes right before its dots
    spans=span([('أ',10,14),('ل',14,18),('م',18,24),(' ',24,26),('\x18',26,32,'\u06a1\u0649'),('ف',30,30),('ي',29,29),(' ',32,34),('ا',34,36)])
    assert P._stored_order_ligatures(spans)=='ألم في ا'
    line={'dir':(0.9976,0.0698),'spans':spans}
    assert P._line_text(line,[],False)=='ألم في ا'


def test_dropped_dot_is_restored_from_the_glyph_trace():
    class FakePage:
        def get_texttrace(self):
            return [{'font':'ABCDEF+B','chars':[(0xfffd,164,(79.7,125.6),(79.7,110,92.3,130)),
                                                (0x634,157,(89.4,119.6),(89.4,110,89.4,130)),     # the dropped three-dot glyph
                                                (0x643,174,(92.3,125.6),(92.3,110,100.0,130))]}]
    blocks=[{'type':0,'lines':[{'dir':(1,0),'spans':[{'font':'B','size':18,'bbox':(79,110,101,130),'chars':[
        {'c':'ك','bbox':(92.3,110,100.0,130),'origin':(92.3,125.6)},
        {'c':'½','bbox':(79.7,110,92.3,130),'origin':(79.7,125.6),'lig':'\u0649\u0631'}]}]}]}]
    learned={('B',157):{'ث':3}}                                        # learned from dots kept on other lines
    P._restore_dropped_dots(FakePage(),blocks,learned)
    chars=blocks[0]['lines'][0]['spans'][0]['chars']
    assert [c['c'] for c in chars]==['ك','½','ث']
    assert P._visual_line(blocks[0]['lines'][0]['spans'])=='كثر'


def test_ordinary_pdf_has_no_ligature_table():
    doc=fitz.open(); page=doc.new_page(); page.insert_text((50,50),'Plain text 123',fontsize=12)
    blocks=page.get_text('rawdict')['blocks']
    assert P._mark_ligature_bodies(doc,page,blocks,{}) is False


def test_adobe_font_diacritic_sits_on_the_left_edge_of_its_letter():
    # التعلُّم and جديداً. in an Adobe Arabic font: the mark is at the left edge of its own letter
    chars=[('ا',121.0,123.4),('ل',118.4,121.0),('ت',115.5,118.4),('ع',109.8,115.5),('ل',107.0,109.8),('\u064f',107.3,107.3),('\u0651',107.3,107.3),('م',99.5,107.0)]
    sp=span(chars); sp[0]['adobe']=True
    out=P._visual_line(sp)
    assert out.replace('\u064f\u0651','\u0651\u064f')=='التعل\u0651\u064fم'
    sp=span([('ج',233.6,239.7),('د',228.2,233.6),('ي',225.6,228.2),('د',220.2,225.6),('ا',218.0,220.3),('\u064b',218.0,218.0),('.',215.0,218.1)]); sp[0]['adobe']=True
    assert P._visual_line(sp)=='جديدا\u064b.'
    # Word keeps its own rule: the shadda of قصّر is on the right edge of the sad
    assert P._visual_line(span([('ق',314.8,322.1),('\u0651',314.8,314.8),('ص',301.3,314.8),('ر',308.5,308.5)]))=='قصّر'
