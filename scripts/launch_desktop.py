import ctypes
import os
import sys
from ctypes import wintypes

class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ('cb', wintypes.DWORD),
        ('lpReserved', wintypes.LPWSTR),
        ('lpDesktop', wintypes.LPWSTR),
        ('lpTitle', wintypes.LPWSTR),
        ('dwX', wintypes.DWORD),
        ('dwY', wintypes.DWORD),
        ('dwXSize', wintypes.DWORD),
        ('dwYSize', wintypes.DWORD),
        ('dwXCountChars', wintypes.DWORD),
        ('dwYCountChars', wintypes.DWORD),
        ('dwFillAttribute', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('wShowWindow', wintypes.WORD),
        ('cbReserved2', wintypes.WORD),
        ('lpReserved2', ctypes.c_char_p),
        ('hStdInput', wintypes.HANDLE),
        ('hStdOutput', wintypes.HANDLE),
        ('hStdError', wintypes.HANDLE),
    ]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('hProcess', wintypes.HANDLE),
        ('hThread', wintypes.HANDLE),
        ('dwProcessId', wintypes.DWORD),
        ('dwThreadId', wintypes.DWORD),
    ]

candidates = ['default', 'WinSta0\\Default', 'Default', '']
for desk in candidates:
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.lpDesktop = desk if desk else None
    pi = PROCESS_INFORMATION()
    exe = os.path.abspath('.venv/Scripts/python.exe')
    main_py = os.path.abspath('src/main.py')
    cmd = f'"{exe}" "{main_py}"'
    res = ctypes.windll.kernel32.CreateProcessW(
        None, cmd, None, None, False, 0, None, os.path.abspath('.'), ctypes.byref(si), ctypes.byref(pi)
    )
    err = ctypes.GetLastError()
    print(f'Desktop "{desk}": res={bool(res)}, PID={pi.dwProcessId}, LastError={err}')
    if res:
        print(f'SUCCESS! Started PID {pi.dwProcessId} on desktop "{desk}"')
        break
