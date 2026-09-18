"""
Sandbox security (Section V.2 points 3, 4).

Four things the sandbox has to hold up under `tests/test_sandbox_security.py`:
  1. import allowlist    -- only whitelisted modules can be imported
  2. path allowlist       -- file access restricted to allowed_directories
  3. timeout               -- handled in sandbox/executor.py, not here
  4. memory limit          -- handled in sandbox/executor.py, not here

Only the standard library is used here (no third-party sandboxing libs).
"""
from __future__ import annotations

import builtins
import os
from typing import Iterable, Set


def check_path_allowed(path: str, allowed_directories: Iterable[str]) -> bool:
    """True if `path` resolves to somewhere inside one of `allowed_directories`.

    `os.path.realpath` collapses `..`, symlinks and relative segments into a
    clean absolute path first, so a trick like "/testbed/../../etc/passwd"
    can't sneak past the string comparison below.
    """
    real_path = os.path.realpath(path)
    for allowed in allowed_directories:
        real_allowed = os.path.realpath(allowed)
        if real_path == real_allowed or real_path.startswith(real_allowed + os.sep):
            return True
    return False


class ImportGuard:
    """Intercepts `__import__`, only letting whitelisted modules through.

    `authorized_imports` entries can be an exact module name ("math") or a
    wildcard covering all of a package's submodules ("math.*").
    """

    def __init__(self, authorized_imports: Iterable[str]):
        self.authorized: Set[str] = set(authorized_imports)
        self._real_import = builtins.__import__

    def _is_authorized(self, module_name: str) -> bool:
        if module_name in self.authorized:
            return True
        top_level = module_name.split(".")[0]
        if top_level in self.authorized:
            return True
        if f"{top_level}.*" in self.authorized:
            return True
        return False

    def guarded_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if not self._is_authorized(name):
            raise ImportError(f"Module '{name}' is not in the authorized imports allowlist")
        return self._real_import(name, globals, locals, fromlist, level)

    def install(self) -> None:
        builtins.__import__ = self.guarded_import

    def uninstall(self) -> None:
        builtins.__import__ = self._real_import


def build_restricted_builtins(allowed_directories: Iterable[str]) -> dict:
    """A copy of the normal builtins, with the dangerous ones removed or wrapped.

    - `open` is replaced with a version that checks the path first.
    - `eval` / `exec` / `compile` / `__import__` are removed: the sandbox itself
      needs `exec` to run the LLM's code once, but the LLM's code should not be
      able to call `exec`/`eval` again from inside to route around the guards
      above (`ImportGuard` already covers plain `import` statements).
    - `input` / `breakpoint` are removed: no interactive prompts from inside
      untrusted code.
    """
    safe_builtins = dict(vars(builtins))
    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if not check_path_allowed(str(file), allowed_directories):
            raise PermissionError(f"Access to path '{file}' is not allowed")
        return real_open(file, mode, *args, **kwargs)

    safe_builtins["open"] = guarded_open

    # __import__ is intentionally left in place here; Sandbox._setup_namespace
    # overwrites it with the ImportGuard's guarded version. The import
    # statement needs *some* callable named __import__ to exist in builtins,
    # so removing it outright breaks even whitelisted imports.
    for name in ("eval", "exec", "compile", "input", "breakpoint"):
        safe_builtins.pop(name, None)

    return safe_builtins
