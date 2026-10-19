"""Business orchestration for ByggLeaf.

Submodules depend only on the standard library, the two approved rendering
libraries, and each other.  They never import ``app`` or ``cli``.  Workspace
scaffolding lives here too: it is a core operation, not an entry-point concern.
Keep this file free of eager imports so the dependency graph stays easy to
audit.
"""
