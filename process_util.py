"""FFmpeg / alt süreçleri güvenli kapatma (zombi ve sızıntı önleme)."""

from __future__ import annotations

import subprocess
from typing import Any

from app_log import get_logger

_log = get_logger("process")


def ffmpeg_kapat(
    proc: subprocess.Popen[Any] | None,
    *,
    nazik: bool = True,
    bekle_q: float = 3.0,
    bekle_term: float = 2.0,
) -> None:
    """
    stdin varsa 'q', sonra terminate, sonra kill; her adımda wait.
    stdout/stderr/stdin kapatılır.
    """
    if proc is None:
        return
    try:
        if proc.poll() is None and nazik and proc.stdin:
            try:
                proc.stdin.write(b"q")
                proc.stdin.flush()
            except OSError:
                pass
            try:
                proc.wait(timeout=bekle_q)
            except subprocess.TimeoutExpired:
                pass
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=bekle_term)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=2)
                except Exception:
                    _log.warning("Süreç kill sonrası hâlâ bekliyor pid=%s", getattr(proc, "pid", "?"))
    except Exception:
        _log.exception("Süreç kapatılamadı")
    for boru in (proc.stdin, proc.stdout, proc.stderr):
        if boru is None:
            continue
        try:
            boru.close()
        except Exception:
            pass
