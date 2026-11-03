"""Lazy loading and version discovery for the isolated PyOpenMagnetics runtime."""

from __future__ import annotations

import importlib
from importlib import metadata
from typing import Any


def load_module() -> tuple[Any | None, dict[str, Any] | None]:
    """Import PyOpenMagnetics and initialize its embedded databases.

    The production Demo does not install this package.  Returning a structured
    error here lets callers show that condition without silently falling back to
    a zero or to the synthetic engine.
    """

    try:
        module = importlib.import_module("PyOpenMagnetics")
    except Exception as exc:  # pragma: no cover - depends on local environment
        return None, {
            "code": "OPENMAGNETICS_UNAVAILABLE",
            "message": f"无法导入 PyOpenMagnetics: {type(exc).__name__}: {exc}",
        }

    if not hasattr(module, "load_databases"):
        return None, {
            "code": "OPENMAGNETICS_API_INCOMPLETE",
            "message": "已导入 PyOpenMagnetics，但缺少 load_databases()。",
        }
    try:
        module.load_databases({})
    except Exception as exc:  # pragma: no cover - depends on local installation
        return None, {
            "code": "OPENMAGNETICS_DATABASE_INIT_FAILED",
            "message": f"OpenMagnetics 数据库初始化失败: {type(exc).__name__}: {exc}",
        }
    return module, None


def version_info(module: Any | None) -> dict[str, Any]:
    if module is None:
        return {
            "package": "PyOpenMagnetics",
            "version": None,
            "mkf_commit": None,
            "mas_commit": None,
        }
    try:
        package_version = metadata.version("PyOpenMagnetics")
    except metadata.PackageNotFoundError:
        package_version = getattr(module, "__version__", None)
    return {
        "package": "PyOpenMagnetics",
        "version": package_version,
        "mkf_commit": getattr(module, "__mkf_commit__", None),
        "mas_commit": getattr(module, "__mas_commit__", None),
    }
