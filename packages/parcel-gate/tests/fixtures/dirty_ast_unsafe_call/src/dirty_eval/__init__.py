from __future__ import annotations


def unsafe_one(code: str) -> object:
    return eval(code)  # noqa


def unsafe_two(code: str) -> object:
    return exec(code)  # noqa


def unsafe_three(code: str) -> object:
    return compile(code, "<string>", "exec")


def unsafe_four(name: str) -> object:
    return __import__(name)
