import os  # allowed when the test passes declared_capabilities={"filesystem"}


def cwd() -> str:
    return os.getcwd()
