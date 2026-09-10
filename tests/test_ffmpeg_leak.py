"""FFmpeg kapatılınca PID ve RSS sıfırlanır (psutil)."""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from process_util import ffmpeg_kapat
from record_session import ffmpeg_yolu


def test_ffmpeg_kapat_zombi_yok() -> None:
    try:
        import psutil
    except ImportError:
        pytest.skip("psutil yok")

    bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    ff = ffmpeg_yolu()
    proc = None
    if ff:
        proc = subprocess.Popen(
            [
                ff,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=160x120:rate=5:duration=60",
                "-f",
                "null",
                "-",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=bayrak,
        )
        time.sleep(0.5)
        if proc.poll() is not None:
            proc = None
    if proc is None:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=bayrak,
        )
        time.sleep(0.3)
    pid = proc.pid
    assert psutil.pid_exists(pid)
    try:
        rss_once = psutil.Process(pid).memory_info().rss
        assert rss_once > 0
    except psutil.Error:
        pytest.skip("süreç bilgisi okunamadı")
    ffmpeg_kapat(proc, nazik=False, bekle_term=2.0)
    time.sleep(0.2)
    assert proc.poll() is not None
    assert not psutil.pid_exists(pid)
