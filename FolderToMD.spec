# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
# PyInstaller one-folder Windows build. Native tools live beside the executable.
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
datas=[]
for name in ('PyMuPDF','Pillow','openpyxl','xlrd','lxml','markdownify','onnxruntime','numpy','pyclipper'):
    datas+=copy_metadata(name)
a=Analysis(['main.py'],pathex=[],binaries=[],datas=datas,hiddenimports=['tkinter','tkinter.ttk','onnxruntime','pyclipper','bidi.algorithm'],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['pytest','docx','pptx','xlsxwriter','xlwt','arabic_reshaper','pandas','matplotlib','sympy','onnxruntime.tools','onnxruntime.transformers','onnxruntime.quantization'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='DocsToMD',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False,manifest='app.manifest')
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='DocsToMD')
