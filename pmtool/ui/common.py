from __future__ import annotations


def id_from_labeled_value(value: str, none_label: str) -> int | None:
    if value == none_label:
        return None
    if ": " not in value:
        return None
    return int(value.split(":", 1)[0])
