# Copyright (C) 2026 Yassin Abd El Aal
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import ctypes, os, subprocess, sys
from ctypes import wintypes as W

def app_root():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]

def resources(): return app_root()/'vendor'

def packaged():
    """Cleanup18: True when running as an installed MSIX package (Microsoft Store). The install
    folder is then read-only, so settings go to the user's local application data instead."""
    if os.name != 'nt': return False
    try:
        length = W.UINT(0)
        # APPMODEL_ERROR_NO_PACKAGE (15700) for an ordinary process; ERROR_INSUFFICIENT_BUFFER (122) when packaged.
        return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) != 15700
    except (AttributeError, OSError):
        return False

def data_dir():
    if packaged():
        p = Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')/'DocsToMD'/'data'
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = app_root()/'data'
    try:
        p.mkdir(exist_ok=True)
        test = p/'.write-test'; test.write_bytes(b''); test.unlink()
    except OSError as e:
        raise RuntimeError('Move the complete FolderToMD folder to a writable location, such as Documents.') from e
    return p

def worker_command(request):
    if getattr(sys, 'frozen', False): return [sys.executable, '--worker', str(request)]
    return [sys.executable, str(app_root()/'main.py'), '--worker', str(request)]

class JobProcess:
    """Owns only this worker and its descendants, including OCR/compatibility processes.
    Launch suspended to close the child-spawn race before Job Object assignment."""
    def __init__(self, command, **kwargs):
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.CreateJobObjectW.restype = W.HANDLE
        k.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
        k.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
        k.TerminateJobObject.argtypes = [W.HANDLE, W.UINT]
        k.CloseHandle.argtypes = [W.HANDLE]
        self.k = k; self.handle = k.CreateJobObjectW(None, None)
        # JOBOBJECT_EXTENDED_LIMIT_INFORMATION (x64): BasicLimitInformation flags at offset 16.
        info = ctypes.create_string_buffer(144)
        ctypes.c_uint32.from_buffer(info, 16).value = 0x2000  # KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.handle, 9, info, len(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.process = subprocess.Popen(command, creationflags=0x08000000 | 0x4, **kwargs)
        if not k.AssignProcessToJobObject(self.handle, int(self.process._handle)):
            self.process.kill(); self.close(); raise ctypes.WinError(ctypes.get_last_error())
        n = ctypes.WinDLL('ntdll')
        n.NtResumeProcess.argtypes = [W.HANDLE]
        if n.NtResumeProcess(int(self.process._handle)) != 0:
            self.close(); raise RuntimeError('Could not start isolated worker')
    def stop(self): self.k.TerminateJobObject(self.handle, 1)
    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle); self.handle = None

def child_environment(temp):
    env = os.environ.copy()
    env.update({'OMP_THREAD_LIMIT': '2', 'OMP_NUM_THREADS': '2', 'TEMP': str(temp), 'TMP': str(temp),
                'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1', 'DO_NOT_TRACK': '1'})
    return env
