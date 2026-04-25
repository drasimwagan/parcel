from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from html import escape
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo


def _is_optional(annotation: Any) -> tuple[bool, Any]:
    """Return (is_optional, inner_type) for `T | None` / `Optional[T]`."""
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1 and len(get_args(annotation)) > 1:
            return True, args[0]
    return False, annotation


def _input_attrs(name: str, *, required: bool, value: Any, kind: str) -> str:
    parts = [f'name="{escape(name)}"', f'type="{kind}"']
    if required:
        parts.append("required")
    if kind == "checkbox":
        if value:
            parts.append("checked")
    elif value is not None and value != "":
        parts.append(f'value="{escape(str(value))}"')
    return " ".join(parts)


def _control_for(
    name: str,
    annotation: Any,
    field: FieldInfo,
    values: dict[str, Any],
    *,
    is_optional: bool,
) -> str:
    extras = field.json_schema_extra or {}
    widget = extras.get("widget") if isinstance(extras, dict) else None
    required = not is_optional and field.is_required()
    raw_value = values.get(name, field.default if field.default is not None else "")

    if widget == "textarea":
        return (
            f'<textarea name="{escape(name)}" '
            f'class="w-full rounded border-gray-300 p-2"'
            f'{" required" if required else ""}>'
            f"{escape(str(raw_value or ''))}</textarea>"
        )

    if annotation is bool:
        return (
            f'<input {_input_attrs(name, required=False, value=bool(raw_value), kind="checkbox")} '
            'class="rounded border-gray-300">'
        )

    if annotation is int:
        return (
            f'<input {_input_attrs(name, required=required, value=raw_value, kind="number")} '
            'step="1" class="w-full rounded border-gray-300">'
        )

    if annotation is float:
        return (
            f'<input {_input_attrs(name, required=required, value=raw_value, kind="number")} '
            'step="any" class="w-full rounded border-gray-300">'
        )

    if annotation is date:
        return (
            f'<input {_input_attrs(name, required=required, value=raw_value, kind="date")} '
            'class="w-full rounded border-gray-300">'
        )

    if annotation is datetime:
        attrs = _input_attrs(name, required=required, value=raw_value, kind="datetime-local")
        return f'<input {attrs} class="w-full rounded border-gray-300">'

    origin = get_origin(annotation)
    if origin is Literal:
        opts = []
        for choice in get_args(annotation):
            sel = " selected" if str(raw_value) == str(choice) else ""
            esc = escape(str(choice))
            opts.append(f'<option value="{esc}"{sel}>{esc}</option>')
        return (
            f'<select name="{escape(name)}" class="w-full rounded border-gray-300"'
            f'{" required" if required else ""}>{"".join(opts)}</select>'
        )

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        opts = []
        for member in annotation:
            sel = " selected" if str(raw_value) == str(member.value) else ""
            opts.append(
                f'<option value="{escape(str(member.value))}"{sel}>{escape(member.name)}</option>'
            )
        return (
            f'<select name="{escape(name)}" class="w-full rounded border-gray-300"'
            f'{" required" if required else ""}>{"".join(opts)}</select>'
        )

    return (
        f'<input {_input_attrs(name, required=required, value=raw_value, kind="text")} '
        'class="w-full rounded border-gray-300">'
    )


def render_form(
    model: type[BaseModel],
    values: dict[str, Any],
    errors: dict[str, list[str]],
) -> str:
    """Render a Tailwind-styled HTML <form> from a Pydantic model.

    `values` pre-fills the inputs (used when re-rendering after a validation
    error). `errors` is `{field_name: [messages, ...]}` from
    `ValidationError.errors()`.
    """
    rows: list[str] = []
    for name, field in model.model_fields.items():
        is_opt, inner = _is_optional(field.annotation)
        control = _control_for(name, inner, field, values, is_optional=is_opt)
        label = field.title or name.replace("_", " ").capitalize()
        helper = ""
        if field.description:
            helper = f'<p class="text-xs text-gray-500 mt-1">{escape(field.description)}</p>'
        err_html = ""
        if name in errors and errors[name]:
            joined = "; ".join(errors[name])
            err_html = f'<p class="text-xs text-red-600 mt-1">{escape(joined)}</p>'
        rows.append(
            f'<div class="mb-3">'
            f'<label class="block text-sm font-medium text-gray-700 mb-1">{escape(label)}</label>'
            f"{control}{helper}{err_html}"
            "</div>"
        )
    return '<form class="space-y-2">' + "".join(rows) + "</form>"
