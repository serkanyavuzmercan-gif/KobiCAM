"""Kısa ömürlü SQLite bağlantıları: WAL + busy timeout."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_kilit = threading.Lock()
_sema: set[str] = set()


def baglan(yol: str | Path) -> sqlite3.Connection:
    """timeout=30, check_same_thread=False, WAL, busy_timeout=30s."""
    hedef = Path(yol)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    bag = sqlite3.connect(str(hedef), timeout=30, check_same_thread=False)
    bag.row_factory = sqlite3.Row
    bag.execute("PRAGMA journal_mode=WAL")
    bag.execute("PRAGMA busy_timeout=30000")
    bag.execute("PRAGMA synchronous=NORMAL")
    return bag


def sema_bir_kez(yol: str | Path, ddl: str | list[str]) -> None:
    """CREATE TABLE IF NOT EXISTS ifadelerini dosya başına bir kez çalıştırır."""
    anahtar = str(Path(yol).resolve())
    with _kilit:
        if anahtar in _sema:
            return
        komutlar = [ddl] if isinstance(ddl, str) else list(ddl)
        with baglan(yol) as bag:
            for sql in komutlar:
                bag.executescript(sql)
            bag.commit()
        _sema.add(anahtar)
