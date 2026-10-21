from foldertomd.boqrows import _boundaries, split_item_rows


def w(text,top,height=20):
    return {'text':text,'top':str(top),'height':str(height),'left':'0','width':'40','conf':'90'}


def fixture():
    # header row + one tall body row; item numbers in column 0 at y 100/220/340
    head=[[w('ITEM',0)],[w('DESCRIPTION',0)],[w('UNIT',0)],[w('QTY',0)]]
    body=[
        [w('1',100),w('2',220),w('3',340)],
        [w('Section',20),w('Pump',100),w('and',130),w('Valve',220),w('Pipe',340),w('end',370)],
        [w('No.',130),w('L.S',250),w('m',370)],
        [w('9',130),w('1',250),w('15',370)],
    ]
    rows=[[' '.join(x['text'] for x in c) for c in head],[' '.join(x['text'] for x in c) for c in body]]
    readings=[]
    for r,cells in enumerate((head,body)):
        for c,words in enumerate(cells):
            readings.append([r,c,(0,0,50,600),words])
    offsets={(r,c):0 for r in (0,1) for c in range(4)}
    box=[(0,0,50,40),(0,0,50,600)]
    readings=[[r,c,box[r],ws] for r,c,_,ws in readings]
    return rows,[[(0,1),(1,2),(2,3),(3,4)]]*2,readings,offsets




def test_boundary_uses_paragraph_gap_above_number():
    # item 2's number sits beside its second line (y 130); its heading line (y 100) follows a gap
    spans=[(0,20),(30,50),(100,120),(130,150),(160,180),(260,280)]
    bounds=_boundaries([30,130,260],20,spans)
    assert bounds[1]==75


def test_boundary_falls_back_without_gap():
    spans=[(0,20),(22,42),(44,64),(66,86)]
    bounds=_boundaries([22,66],20,spans)
    assert bounds==[22-12,66-12]


def test_heading_line_goes_with_its_own_item():
    rows,spans,readings,offsets=fixture()
    for r,c,b,ws in readings:
        if r==1 and c==1:
            ws[:]=[w('Section',20),w('Pump',100),w('and',130),w('Valve',190),w('head',220),w('Pipe',340),w('end',370)]
    rows[1][1]='Section Pump and Valve head Pipe end'
    out,sp,rs,n=split_item_rows(rows,spans,{},readings,offsets,4)
    assert n==1
    assert out[3][1]=='Valve head'


def test_first_anchor_never_takes_section_heading():
    # a gap sits above the first number, but that text is the section heading
    spans=[(0,20),(100,120),(130,150),(260,280)]
    bounds=_boundaries([100,260],20,spans)
    assert bounds[0]==100-12
