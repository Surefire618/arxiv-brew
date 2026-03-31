"""arxiv-brew: keyword-based arXiv paper filtering and digest generation."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("arxiv-brew")
except PackageNotFoundError:
    # Fallback: parse pyproject.toml directly
    from pathlib import Path as _Path
    import re as _re
    _toml = _Path(__file__).parent.parent / "pyproject.toml"
    if _toml.exists():
        _m = _re.search(r'version\s*=\s*"([^"]+)"', _toml.read_text())
        __version__ = _m.group(1) if _m else "dev"
    else:
        __version__ = "dev"

USER_AGENT = f"arxiv-brew/{__version__} (research-tool)"
