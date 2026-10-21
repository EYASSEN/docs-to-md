# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extract an MSI via its read-only database tables and 7-Zip; never run MSI actions."""
import ctypes,shutil,subprocess
from ctypes import wintypes as W
from pathlib import Path

def extract(msi_path,destination,seven):
    api=ctypes.WinDLL('msi');handle=W.UINT()
    api.MsiOpenDatabaseW.argtypes=[W.LPCWSTR,ctypes.c_void_p,ctypes.POINTER(W.UINT)]
    code=api.MsiOpenDatabaseW(str(msi_path),None,ctypes.byref(handle))
    if code:raise RuntimeError('Cannot read MSI database: '+str(code))
    api.MsiDatabaseOpenViewW.argtypes=[W.UINT,W.LPCWSTR,ctypes.POINTER(W.UINT)]
    api.MsiViewFetch.argtypes=[W.UINT,ctypes.POINTER(W.UINT)]
    api.MsiRecordGetStringW.argtypes=[W.UINT,W.UINT,W.LPWSTR,ctypes.POINTER(W.DWORD)]
    def query(sql,count):
        view=W.UINT();code=api.MsiDatabaseOpenViewW(handle,sql,ctypes.byref(view))
        if code:raise RuntimeError('MSI query failed: '+str(code))
        api.MsiViewExecute(view,0);rows=[]
        while True:
            record=W.UINT();code=api.MsiViewFetch(view,ctypes.byref(record))
            if code==259:break
            if code:raise RuntimeError('MSI fetch failed: '+str(code))
            values=[]
            for index in range(1,count+1):
                buf=ctypes.create_unicode_buffer(32768);size=W.DWORD(32767)
                api.MsiRecordGetStringW(record,index,buf,ctypes.byref(size));values.append(buf.value)
            rows.append(values);api.MsiCloseHandle(record)
        api.MsiCloseHandle(view);return rows
    try:
        dirs={r[0]:r[1:] for r in query('SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`',3)}
        components=dict(query('SELECT `Component`, `Directory_` FROM `Component`',2))
        files=query('SELECT `File`, `Component_`, `FileName` FROM `File`',3)
    finally:api.MsiCloseHandle(handle)
    def directory(key):
        if key=='TARGETDIR' or key not in dirs:return Path()
        parent,name=dirs[key];name=name.split(':')[0].split('|')[-1]
        return directory(parent)/(name if name!='.' else '')
    flat=msi_path.parent/'lo-cab-files';flat.mkdir(exist_ok=True)
    subprocess.run([str(seven),'x',str(msi_path),'-o'+str(flat),'-y'],check=True,stdout=subprocess.DEVNULL)
    routes={fid:directory(components[component])/name.split('|')[-1] for fid,component,name in files}
    main=next(path for path in routes.values() if path.name=='soffice.exe')
    install_root=main.parent.parent
    count=0
    for fid,path in routes.items():
        if not path.is_relative_to(install_root):continue
        src=flat/fid
        if not src.exists():raise RuntimeError('Missing extracted MSI file: '+fid)
        dest=destination/path.relative_to(install_root);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);count+=1
    print('Extracted LibreOffice files:',count,flush=True)

if __name__=='__main__':
    import sys
    extract(*(Path(x).resolve() for x in sys.argv[1:]))
