"""
Sandbox security mechanisms (Section V.2, points 3 & 4).

Four dimensions, all implemented:
  1. Import restriction — only whitelisted modules can be imported   DONE
  2. Filesystem restriction — only allowed_directories are reachable  DONE
  3. Execution timeout — enforced in executor.py via signal.alarm     DONE
  4. Memory limit — enforced in executor.py via resource.setrlimit    DONE

Standard library only (the PDF explicitly forbids third-party
libraries like RestrictedPython).
"""
from __future__ import annotations

import builtins as _builtins_module
import os
from typing import Iterable, Set


class ImportGuard:
    """Intercepts __import__, only allowing modules on the whitelist."""

    def __init__(self, authorized_imports: Iterable[str]):
        self.authorized: Set[str] = set(authorized_imports)
        self._real_import = _builtins_module.__import__

    def _is_authorized(self, module_name: str) -> bool:
        if module_name in self.authorized:
            return True
        top_level = module_name.split(".")[0]
        if f"{top_level}.*" in self.authorized:
            return True
        return False

    def guarded_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if not self._is_authorized(name):
            raise ImportError(
                f"[SANDBOX] Module '{name}' is not in the authorized_imports allowlist."
            )
        return self._real_import(name, globals, locals, fromlist, level)

    def install(self) -> None:
        _builtins_module.__import__ = self.guarded_import

    def uninstall(self) -> None:
        _builtins_module.__import__ = self._real_import


def check_path_allowed(path: str, allowed_directories: Iterable[str]) -> bool:
    """Check whether `path` falls within one of allowed_directories.

    Resolves ".." and symlinks first (os.path.realpath) to defend against
    path traversal, and matches against the directory PLUS a trailing
    separator so a look-alike neighbor like "/testbed_backup" is never
    mistaken for being inside "/testbed".
    """
    real_path = os.path.realpath(path)
    for allowed_dir in allowed_directories:
        real_allowed = os.path.realpath(allowed_dir)
        if real_path == real_allowed or real_path.startswith(real_allowed + os.sep):
            return True
    return False


def build_restricted_builtins(allowed_directories: Iterable[str]) -> dict:
    """Return a copy of the builtins namespace with dangerous entries
    removed or replaced by safe, checked versions.

    - eval / exec / compile: removed entirely. The sandbox itself uses its
      own exec() call (in executor.py) to run the LLM's code, but code
      RUNNING INSIDE the sandbox must not be able to call exec()/eval()
      again -- that would let it build a string at runtime and execute it,
      sidestepping the ImportGuard and the checked open() below.
    - __import__: left out here on purpose; executor.py installs
      ImportGuard.guarded_import in its place right after calling this
      function, so import restriction stays in one place (security.py's
      ImportGuard), not duplicated here.
    - open: replaced with a version that checks the requested path against
      `allowed_directories` (via check_path_allowed) before allowing it.
    """
    allowed_dirs = list(allowed_directories)
    real_open = _builtins_module.open

    def checked_open(file, mode="r", *args, **kwargs):
        if not check_path_allowed(str(file), allowed_dirs):
            raise PermissionError(
                f"[SANDBOX] Path '{file}' is outside the allowed directories: {allowed_dirs}"
            )
        return real_open(file, mode, *args, **kwargs)

    safe_builtins = {
        name: value
        for name, value in vars(_builtins_module).items()
        if name not in ("eval", "exec", "compile", "__import__")
    }
    safe_builtins["open"] = checked_open
    return safe_builtins