# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import pefile

def closure(root):
    table={p.name.lower():p for p in root.iterdir() if p.is_file()}
    queue=['tesseract.exe'];seen=set();system=set()
    while queue:
        name=queue.pop()
        if name in seen:continue
        seen.add(name)
        pe=pefile.PE(str(table[name]))
        for entry in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]):
            dep=entry.dll.decode().lower()
            if dep in table:queue.append(dep)
            else:system.add(dep)
        pe.close()
    return sorted(seen),sorted(system)

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]/'vendor'/'tesseract'
    print('\n'.join(closure(root)[0]));print('Windows APIs:',closure(root)[1])
