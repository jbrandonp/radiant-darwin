"""
Script de lancement interactif de l'application CAD Studio sur le bureau utilisateur Windows.
Garantit le rattachement du processus à la station interactive WinSta0\\Default.
"""

from __future__ import annotations
import os
import sys
import ctypes
from ctypes import wintypes


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_char_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def launch_cad_studio() -> bool:
    """Lance CAD Studio sur le bureau Windows interactif de l'utilisateur."""
    root_dir = os.path.abspath(os.path.dirname(__file__))
    python_exe = os.path.join(root_dir, ".venv", "Scripts", "python.exe")
    main_script = os.path.join(root_dir, "src", "main.py")

    cmd_line = f'"{python_exe}" "{main_script}"'

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(STARTUPINFOW)
    si.lpDesktop = r"WinSta0\Default"
    si.dwFlags = 1  # STARTF_USESHOWWINDOW
    si.wShowWindow = 1  # SW_SHOWNORMAL

    pi = PROCESS_INFORMATION()

    k32 = ctypes.windll.kernel32
    # CREATE_NEW_PROCESS_GROUP = 0x00000200
    creation_flags = 0x00000200

    success = k32.CreateProcessW(
        None,
        cmd_line,
        None,
        None,
        False,
        creation_flags,
        None,
        root_dir,
        ctypes.byref(si),
        ctypes.byref(pi)
    )

    if success:
        print(f"CAD Studio démarré avec succès sur le bureau interactif (PID: {pi.dwProcessId}).")
        k32.CloseHandle(pi.hProcess)
        k32.CloseHandle(pi.hThread)
        return True
    else:
        err = k32.GetLastError()
        print(f"Échec du démarrage de CAD Studio (Erreur Win32: {err}).")
        return False


if __name__ == "__main__":
    launch_cad_studio()
