import os  # triggers ast.blocked_import.os without a declared capability


def cwd() -> str:
    return os.getcwd()
