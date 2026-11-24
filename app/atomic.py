"""Replace a file in one rename, so a reader or a crash never sees half of it.

A plain helper with no imports from the app, so pure and core modules alike
can use it.
"""
from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path


@contextmanager
def replacing(target: Path, unique: bool = False) -> Iterator[Path]:
    """Yield a hidden part path next to `target` for the caller to fill; when
    the block ends cleanly, the part replaces `target` in one rename. If the
    block or the rename raises, the part is removed and `target` is untouched.

    The part is named ".<name>.part", which the link, the library walk and the
    companion's scanner all skip. With `unique`, the process and thread are
    added to the name, for writers that may race on the same target.
    """
    tag = f".{os.getpid()}.{threading.get_ident()}" if unique else ""
    part = target.with_name(f".{target.name}{tag}.part")
    try:
        yield part
        os.replace(part, target)
    except BaseException:
        with suppress(OSError):
            part.unlink()
        raise
