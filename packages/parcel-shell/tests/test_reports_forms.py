from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from parcel_shell.reports.forms import render_form


class StrParams(BaseModel):
    q: str | None = None


class IntParams(BaseModel):
    n: int = 0


class FloatParams(BaseModel):
    f: float = 1.0


class BoolParams(BaseModel):
    on: bool = False


class DescribedParams(BaseModel):
    q: str | None = Field(default=None, description="Search by name")


def test_render_form_str_input() -> None:
    html = render_form(StrParams, values={}, errors={})
    assert "<form" in html
    assert 'name="q"' in html
    assert 'type="text"' in html


def test_render_form_int_input() -> None:
    html = render_form(IntParams, values={}, errors={})
    assert 'name="n"' in html
    assert 'type="number"' in html


def test_render_form_float_input() -> None:
    html = render_form(FloatParams, values={}, errors={})
    assert 'name="f"' in html
    assert 'type="number"' in html
    assert 'step="any"' in html


def test_render_form_bool_input() -> None:
    html = render_form(BoolParams, values={}, errors={})
    assert 'name="on"' in html
    assert 'type="checkbox"' in html


def test_render_form_optional_drops_required() -> None:
    html = render_form(StrParams, values={}, errors={})
    snippet = html[html.index('name="q"') :]
    snippet = snippet[: snippet.index(">") + 1]
    assert "required" not in snippet


def test_render_form_description_renders_helper() -> None:
    html = render_form(DescribedParams, values={}, errors={})
    assert "Search by name" in html


def test_render_form_value_prefilled() -> None:
    html = render_form(StrParams, values={"q": "alice"}, errors={})
    assert 'value="alice"' in html


def test_render_form_errors_rendered_inline() -> None:
    html = render_form(IntParams, values={"n": "abc"}, errors={"n": ["must be a number"]})
    assert "must be a number" in html


# --- Task 6 cases (extended widgets) -----------------------------------------


class DateParams(BaseModel):
    d: date | None = None


class DateTimeParams(BaseModel):
    when: datetime | None = None


class LiteralParams(BaseModel):
    mode: Literal["draft", "final"] = "draft"


class Color(str, Enum):
    RED = "red"
    BLUE = "blue"


class EnumParams(BaseModel):
    c: Color = Color.RED


class TextareaParams(BaseModel):
    notes: str | None = Field(default=None, json_schema_extra={"widget": "textarea"})


def test_render_form_date_input() -> None:
    html = render_form(DateParams, values={}, errors={})
    assert 'type="date"' in html


def test_render_form_datetime_input() -> None:
    html = render_form(DateTimeParams, values={}, errors={})
    assert 'type="datetime-local"' in html


def test_render_form_literal_select() -> None:
    html = render_form(LiteralParams, values={}, errors={})
    assert "<select" in html
    assert 'value="draft"' in html
    assert 'value="final"' in html


def test_render_form_enum_select() -> None:
    html = render_form(EnumParams, values={}, errors={})
    assert "<select" in html
    assert 'value="red"' in html
    assert 'value="blue"' in html


def test_render_form_textarea_widget() -> None:
    html = render_form(TextareaParams, values={}, errors={})
    assert "<textarea" in html
    assert 'name="notes"' in html
