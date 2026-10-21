# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded pixel checks of weak inline numeric words in Arabic scan cells.

The baseline is never replaced by a digit whitelist or a document answer. Latin
letters and punctuation compete with digits. Ambiguous glyphs keep the baseline.
"""
import base64,io,re,unicodedata
from functools import lru_cache
from PIL import Image,ImageOps,ImageChops,ImageStat
from .ocrselect import box,confidence,words,numeric,number_tokens,mean_confidence
from .scanglyphs import references,components,ranked_shape,digit_parts

ARABIC=re.compile(r'[\u0621-\u064a]')
UNIT=re.compile(r'^(?:سم|مم|م|كم|بار|جم|كجم|طن|متر|لتر|cm|mm|m|km|bar|kg|%|٪)[²³٢٣]?$')
DIGITS='٠١٢٣٤٥٦٧٨٩'


@lru_cache(maxsize=1)
def glyph_references():
    from .scan_number_templates import TEMPLATES
    result=list(references())
    for char,data,ratio in TEMPLATES:
        image=Image.open(io.BytesIO(base64.b64decode(data))).convert('L')
        energy=ImageStat.Stat(ImageChops.multiply(image,image)).sum[0]
        result.append((char,(image,ratio,energy)))
    return result


def plain(value):
    return ''.join(c for c in value if unicodedata.category(c)!='Cf').strip()


def _rank(image):
    refs=glyph_references()
    return ranked_shape(image,refs,{char for char,_ in refs})


def _shape_number(image,margin=.06):
    parts=digit_parts(image)
    if not 2<=len(parts)<=3:return None
    output=[]
    for x0,y0,x1,y1,_ in parts:
        ranked=_rank(image.crop((x0,y0,x1,y1)))
        if (len(ranked)<2 or ranked[0][0] not in DIGITS or ranked[0][1]<.75
                or ranked[0][1]-ranked[1][1]<margin):return None
        output.append(ranked[0][0])
    return ''.join(output)


def _nearby_unit(word,primary):
    a=box(word);height=a[3]-a[1];cy=(a[1]+a[3])/2
    same=[w for w in primary if w is not word
          and abs((box(w)[1]+box(w)[3])/2-cy)<.8*height]
    if sum(bool(ARABIC.search(w.get('text',''))) for w in same)<3:return False
    return any(UNIT.fullmatch(plain(w['text']).strip('،؛:,.()'))
               and min(abs(box(w)[2]-a[0]),abs(box(w)[0]-a[2]))<2*height
               for w in same)


def _punctuated_number(image,old,run,png):
    """Recover a false terminal digit only when pixels identify trailing punctuation.

    The numeric crop needs two ordinary, agreeing OCR reads above 90. Leading
    zeroes and the numeric prefix are retained; signs/decimals/fractions never
    enter this branch. Both comma and closing parenthesis remain in the result.
    """
    value=plain(old)
    match=re.fullmatch(r'([()،؛,]*)([0-9]{2,5})([()،؛,]*)',value)
    if not match:return None
    digits=match[2]
    if digits.startswith('0'):return None
    parts=components(image)
    if not 3<=len(parts)<=8:return None
    punctuation=[]
    for part in reversed(parts):
        ranked=_rank(image.crop(part[:4]))
        if (len(ranked)<2 or ranked[0][0] not in '،;,)'
                or ranked[0][1]<.8 or ranked[0][1]-ranked[1][1]<.10):break
        punctuation.insert(0,(part,ranked[0][0]))
    # One tiny blob is insufficient: require separately recognized comma and
    # closing bracket, whose geometry accounts for the false final digit.
    if len(punctuation)!=2 or punctuation[0][1] not in '،;,' or punctuation[1][1]!=')':return None
    kept=parts[:-2]
    if len(kept)!=len(digits)-1 or not 1<=len(kept)<=4:return None
    tallest=max(p[3]-p[1] for p in kept)
    comma,bracket=(p[0] for p in punctuation)
    if comma[3]-comma[1]>.6*tallest or bracket[3]-bracket[1]<.8*tallest:return None
    if punctuation[0][0][0]<=max(p[2] for p in kept):return None
    x0=min(p[0] for p in kept);y0=min(p[1] for p in kept)
    x1=max(p[2] for p in kept);y1=max(p[3] for p in kept)
    crop=ImageOps.expand(image.crop((max(0,x0-2),max(0,y0-2),min(image.width,x1+2),min(image.height,y1+2))),border=12,fill='white')
    values=[]
    for variant in (crop,ImageOps.grayscale(crop).point(lambda p:0 if p<160 else 255)):
        reading=words(run(png(variant),['-l','eng','--psm','7','tsv']))
        candidate=plain(' '.join(w['text'] for w in reading))
        if not candidate.isascii() or not candidate.isdecimal() or mean_confidence(reading)<90:return None
        values.append(candidate)
    if values[0]!=values[1] or values[0]!=digits[:-1]:return None
    return values[0]+''.join(char for _,char in punctuation)


def refine_numeric_words(image,primary,run,png,language='ara+eng'):
    """Mutate only the checked TSV words; return number of changed words.

    Coordinates are those of the padded cell image supplied to Tesseract. The
    caller rebuilds the cell without moving words between rows or columns.
    Limit to 12 weak words and at most two OCR calls per punctuation candidate.
    """
    if not language.startswith('ara') or len(primary)<5:return 0
    text=' '.join(w.get('text','') for w in primary)
    if len(ARABIC.findall(text))<3*sum(c.isascii() and c.isalpha() for c in text):return 0
    changed=attempts=0
    for word in primary:
        old=plain(word.get('text',''))
        if confidence(word)>=75 or not old or len(old)>7:continue
        letters=bool(re.fullmatch(r'[A-Za-z]{2,3}',old))
        punctuated=bool(re.fullmatch(r'[()،؛,]*[0-9]{2,5}[()،؛,]*',old))
        if not (letters or punctuated) or attempts>=12:continue
        if letters and not _nearby_unit(word,primary):continue
        attempts+=1
        x0,y0,x1,y1=box(word)
        if x1<=x0 or y1<=y0 or x1-x0>6*(y1-y0):continue
        crop=image.crop((max(0,x0-3),max(0,y0-3),min(image.width,x1+3),min(image.height,y1+3)))
        candidate=None
        if letters:
            readings=[_shape_number(ImageOps.grayscale(crop).point(lambda p:0 if p<threshold else 255),margin)
                      for threshold,margin in ((128,.06),(160,.04))]
            if readings[0] and readings[0]==readings[1]:candidate=readings[0]
        elif punctuated:
            candidate=_punctuated_number(crop,old,run,png)
        if candidate and number_tokens(candidate)!=number_tokens(old):
            word['text']=candidate
            # Shape agreement is not an OCR confidence score. Retain the
            # original confidence so warnings remain conservative.
            changed+=1
    return changed
