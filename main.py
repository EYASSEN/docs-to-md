# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Desktop entry point. --convert and --worker are for reproducible acceptance tests."""
import argparse,json,os,sys,threading
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description='Docs to MD portable offline converter')
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--convert',type=Path)
    parser.add_argument('--result',type=Path)
    parser.add_argument('--language',choices=['ara','eng','ara+eng'],default='ara+eng')
    parser.add_argument('--ocr',choices=['auto','off'],default='auto')
    parser.add_argument('--timeout',type=float,default=3600)
    parser.add_argument('--cancel-after',type=float)
    parser.add_argument('--self-check',type=Path)
    args=parser.parse_args()
    if args.worker:
        # Defense in depth for Python readers: there is no runtime networking API.
        import socket
        def offline(*a,**kw):raise OSError('Document processing is offline')
        socket.create_connection=offline; socket.socket.connect=offline; socket.socket.connect_ex=offline
        from foldertomd.dispatch import extract
        extract(json.loads(args.worker.read_text(encoding='utf-8')));return 0
    if args.self_check:
        from foldertomd.ocr import preflight
        from foldertomd.runtime import resources
        import subprocess,platform
        import tkinter, pymupdf, PIL, xlrd
        tess=preflight()
        r=subprocess.run([str(tess/'tesseract.exe'),'--version'],capture_output=True,creationflags=0x08000000)
        args.self_check.write_text(json.dumps({'platform':platform.platform(),'executable':sys.executable,'frozen':getattr(sys,'frozen',False),'tesseract':r.stdout.decode(errors='replace'),'legacy_backend':(resources()/'poi'/'classes'/'LegacyReader.class').is_file()},indent=2),encoding='utf-8');return r.returncode
    if args.convert:
        from foldertomd.engine import run_job
        from foldertomd.paths import atomic_json
        cancel=threading.Event()
        if args.cancel_after:threading.Timer(args.cancel_after,cancel.set).start()
        try:
            result=run_job(args.convert,{'language':args.language,'ocr':args.ocr,'timeout':args.timeout},cancel)
            if args.result:atomic_json(args.result,result)
            return 0
        except Exception as e:
            if args.result:atomic_json(args.result,{'error':str(e)})
            return 1
    from foldertomd.gui import main as gui
    gui();return 0

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
