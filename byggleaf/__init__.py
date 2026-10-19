"""ByggLeaf — a deliberately small static site generator.

The package root is only a compatibility surface: it re-exports the canonical
version from :mod:`byggleaf.core.version` and never imports an entry module.

Dependency direction (enforced by tests/test_architecture.py):

    app.py  ->  cli.py, core/*
    cli.py  ->  standard library
    core/*  ->  core/*, standard library, markdown, jinja2

Nothing ever points back towards app.py.  The only entry point is the installed
``byggleaf`` console script; the package intentionally has no ``__main__.py``.
"""

from .core.version import VERSION as __version__

__all__ = ["__version__"]
