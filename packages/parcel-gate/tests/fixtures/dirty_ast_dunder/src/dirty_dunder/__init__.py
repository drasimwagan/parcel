from __future__ import annotations


def leak() -> object:
    # triggers ast.dunder_escape.__subclasses__ and ast.dunder_escape.__class__
    return ().__class__.__subclasses__()
