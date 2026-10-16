"""
Script de lancement interactif de l'application CAD Studio sur le bureau utilisateur.
Sur Windows : rattachement du processus à la station interactive WinSta0\\Default.
Sur Linux / macOS : lancement standard en sous-processus détaché.
Architecture 100% portable et typée.
"""

from __future__ import annotations
import os
import sys
import subprocess
from typing import Optional


def launch_cad_studio() -> bool:
    """Lance CAD Studio sur le bureau interactif de l'utilisateur."""
    root_dir = os.path.abspath(os.path.dirname(__file__))
    
    # Détection de l'exécutable Python
    python_exe: str = sys.executable
    if sys.platform == "win32":
        venv_python = os.path.join(root_dir, ".venv", "Scripts", "python.exe")
        if os.path.exists(venv_python):
            python_exe = venv_python
    else:
        venv_python = os.path.join(root_dir, ".venv", "bin", "python")
        if os.path.exists(venv_python):
            python_exe = venv_python

    main_script = os.path.join(root_dir, "src", "main.py")

    # Sur les plateformes non-Windows, lancer directement via subprocess
    if sys.platform != "win32":
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = root_dir + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.Popen(
                [python_exe, "-m", "src.main"],
                cwd=root_dir,
                env=env,
                start_new_session=True
            )
            print(f"CAD Studio démarré avec succès (PID: {proc.pid}).")
            return True
        except Exception as exc:
            print(f"Échec du démarrage de CAD Studio: {exc}")
            return False

    # Sur Windows : rattachement Win32 explicite à WinSta0\\Default
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

    os.environ["PYTHONPATH"] = root_dir + os.pathsep + os.environ.get("PYTHONPATH", "")
    cmd_line = f'"{python_exe}" -m src.main'

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(STARTUPINFOW)
    si.lpDesktop = r"WinSta0\Default"
    si.dwFlags = 1  # STARTF_USESHOWWINDOW
    si.wShowWindow = 1  # SW_SHOWNORMAL

    pi = PROCESS_INFORMATION()

    k32 = ctypes.windll.kernel32
    creation_flags = 0x00000200  # CREATE_NEW_PROCESS_GROUP

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
