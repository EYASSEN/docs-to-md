from foldertomd.boqrows import split_item_rows


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


def test_tall_body_row_is_split_by_item_number():
    rows,spans,readings,offsets=fixture()
    out,sp,rs,n=split_item_rows(rows,spans,{},readings,offsets,4)
    assert n==1
    assert out[0][0]=='ITEM'
    assert out[1]==['','Section','','']
    assert out[2]==['1','Pump and','No.','9']
    assert out[3]==['2','Valve','L.S','1']
    assert out[4]==['3','Pipe end','m','15']
    assert len(sp)==len(out)


def test_rows_without_numbering_column_are_untouched():
    rows,spans,readings,offsets=fixture()
    for r,c,b,ws in readings:
        if r==1 and c==0:ws[:]=[w('Alpha',100),w('Beta',220)]
    rows[1][0]='Alpha Beta'
    out,sp,rs,n=split_item_rows(rows,spans,{},readings,offsets,4)
    assert n==0 and out==rows


def test_spanned_cells_block_the_split_and_later_rowspans_shift():
    rows,spans,readings,offsets=fixture()
    out,sp,rs,n=split_item_rows(rows,spans,{(1,0):2},readings,offsets,4)
    assert n==0
    rows,spans,readings,offsets=fixture()
    rows.append(['x','y','z','t']);spans.append(spans[0])
    out,sp,rs,n=split_item_rows(rows,spans,{(2,0):2},readings,offsets,4)
    assert n==1 and rs=={(5,0):2}


def test_rewritten_cell_is_not_split():
    rows,spans,readings,offsets=fixture()
    rows[1][3]='9 1 15 corrected'
    out,sp,rs,n=split_item_rows(rows,spans,{},readings,offsets,4)
    assert n==0
