from sqlalchemy import text  # triggers ast.raw_sql without the raw_sql capability


def q() -> object:
    return text("SELECT 1")
