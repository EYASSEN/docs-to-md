# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
import html, re
from urllib.parse import quote

def text(value):
    return html.escape(str(value), quote=False).replace('\\', '\\\\').replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')

def cell(value):
    return text('' if value is None else value).replace('|', '\\|').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')

class RuledRows(list):
    """Scan cells with pixel-established spans; only origin cells are emitted."""
    def __init__(self, rows, spans, rowspans=None):
        super().__init__(rows); self.spans=spans; self.rowspans=dict(rowspans or {})

    def map_cells(self, function):
        result=RuledRows([[function(c) for c in row] for row in self], self.spans, self.rowspans)
        if hasattr(self,'ocr_review'):result.ocr_review=dict(self.ocr_review)
        return result


def table(rows):
    spans=getattr(rows,'spans',None)
    rowspans=getattr(rows,'rowspans',{})
    rows = list(rows)
    if not rows: return ''
    if spans and (rowspans or any(last-first>1 for row in spans for first,last in row)):
        rendered=['<table>']
        for r,(row,edges) in enumerate(zip(rows,spans)):
            cells=[]
            for first,last in edges:
                value=html.escape(str(row[first]),quote=False).replace('\r\n','\n').replace('\r','\n').replace('\n','<br>')
                attribute=f' colspan="{last-first}"' if last-first>1 else ''
                height=rowspans.get((r,first),1)
                if height>1:attribute+=f' rowspan="{height}"'
                cells.append(f'<td{attribute}>{value}</td>')
            rendered.append('<tr>'+''.join(cells)+'</tr>')
        return '\n'.join(rendered+['</table>'])+'\n\n'
    n = max(map(len, rows))
    rendered = ['| ' + ' | '.join(cell(x) for x in (list(row) + ['']*(n-len(row)))) + ' |' for row in rows]
    rendered.insert(1, '| ' + ' | '.join(['---']*n) + ' |')
    return '\n'.join(rendered)+'\n\n'

def url(path): return quote(str(path).replace('\\', '/'), safe='/.:#')

def safe_link(target):
    return bool(re.match(r'^(https?://|mailto:|#)', target, re.I))
