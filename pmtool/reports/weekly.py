from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence


def today_text() -> str:
    return date.today().isoformat()


def generate_weekly_project_report(
    output_path: str | Path | None = None,
    *,
    project_title: str | None = None,
    project_team: str | None = None,
    date_value: str | None = None,
    planned_items: Sequence[str] | None = None,
    achieved_items: Sequence[str] | None = None,
    not_achieved_items: Sequence[str] | None = None,
    status_text: str | None = None,
    delay_measures: Sequence[str] | None = None,
    risks: Sequence[str] | None = None,
    risk_measures: Sequence[str] | None = None,
    project_risks: Sequence[dict[str, str]] | None = None,
    task_risks: Sequence[dict[str, str]] | None = None,
    next_milestone: str | None = None,
    next_milestone_date: str | None = None,
) -> Path:
    """Generate a weekly project report markdown file in a strict template format."""

    report_md = build_weekly_project_report_markdown(
        project_title=project_title,
        project_team=project_team,
        date_value=date_value,
        planned_items=planned_items,
        achieved_items=achieved_items,
        not_achieved_items=not_achieved_items,
        status_text=status_text,
        delay_measures=delay_measures,
        risks=risks,
        risk_measures=risk_measures,
        project_risks=project_risks,
        task_risks=task_risks,
        next_milestone=next_milestone,
        next_milestone_date=next_milestone_date,
    )

    if output_path is None:
        output_path = Path(f"wochenbericht_{today_text().replace('-', '')}.md")
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_md, encoding="utf-8")
    return output_path


def build_weekly_project_report_markdown(
    *,
    project_title: str | None = None,
    project_team: str | None = None,
    date_value: str | None = None,
    planned_items: Sequence[str] | None = None,
    achieved_items: Sequence[str] | None = None,
    not_achieved_items: Sequence[str] | None = None,
    status_text: str | None = None,
    delay_measures: Sequence[str] | None = None,
    risks: Sequence[str] | None = None,
    risk_measures: Sequence[str] | None = None,
    project_risks: Sequence[dict[str, str]] | None = None,
    task_risks: Sequence[dict[str, str]] | None = None,
    next_milestone: str | None = None,
    next_milestone_date: str | None = None,
) -> str:
    """Build weekly project report markdown and omit empty sections."""

    def _is_placeholder_text(value: str) -> bool:
        return value.strip().startswith("[Platzhalter:") and value.strip().endswith("]")

    def _clean_items(values: Sequence[str] | None) -> list[str]:
        cleaned = [str(value).strip() for value in (values or []) if str(value).strip()]
        return [value for value in cleaned if not _is_placeholder_text(value)]

    def _bullet_lines(values: Sequence[str] | None) -> str:
        cleaned = _clean_items(values)
        if not cleaned:
            return ""
        return "\n".join(f"- {value}" for value in cleaned)

    def _risk_table(rows: Sequence[dict[str, str]] | None) -> str:
        header = "| Risiko | Wahrscheinlichkeit | Ausmaß | Gegenmaßnahme |"
        divider = "| --- | --- | --- | --- |"
        if not rows:
            return ""

        normalized_rows = []
        for row in rows:
            risk = str(row.get("risk", "")).strip()
            probability = str(row.get("probability", "")).strip()
            impact = str(row.get("impact", "")).strip()
            countermeasure = str(row.get("countermeasure", "")).strip()
            if not risk or _is_placeholder_text(risk):
                continue
            normalized_rows.append(
                (
                    risk,
                    probability or "-",
                    impact or "-",
                    countermeasure or "-",
                )
            )

        if not normalized_rows:
            return ""

        body = "\n".join(f"| {risk} | {probability} | {impact} | {countermeasure} |" for risk, probability, impact, countermeasure in normalized_rows)
        return "\n".join([header, divider, body])

    def _legacy_risk_rows(
        old_risks: Sequence[str] | None,
        old_measures: Sequence[str] | None,
    ) -> list[dict[str, str]]:
        legacy_rows: list[dict[str, str]] = []
        max_len = max(len(old_risks or []), len(old_measures or []))
        for idx in range(max_len):
            risk = ""
            if old_risks and idx < len(old_risks):
                risk = (old_risks[idx] or "").strip()
            if not risk:
                continue
            countermeasure = ""
            if old_measures and idx < len(old_measures):
                countermeasure = (old_measures[idx] or "").strip()
            legacy_rows.append(
                {
                    "risk": risk,
                    "probability": "-",
                    "impact": "-",
                    "countermeasure": countermeasure or "-",
                }
            )
        return legacy_rows

    project_title_text = (project_title or "").strip()
    project_team_text = (project_team or "").strip()
    date_text = (date_value or "").strip()
    planned_lines = _bullet_lines(planned_items)
    achieved_lines = _bullet_lines(achieved_items)
    not_achieved_lines = _bullet_lines(not_achieved_items)
    status_value = (status_text or "").strip()
    if _is_placeholder_text(status_value):
        status_value = ""
    delay_lines = _bullet_lines(delay_measures)
    project_risk_rows = list(project_risks or [])
    task_risk_rows = list(task_risks or [])
    if not task_risk_rows:
        task_risk_rows = _legacy_risk_rows(risks, risk_measures)
    project_risk_table = _risk_table(project_risk_rows)
    task_risk_table = _risk_table(task_risk_rows)
    milestone_text = (next_milestone or "").strip()
    milestone_date_text = (next_milestone_date or "").strip()
    if _is_placeholder_text(milestone_text):
        milestone_text = ""
    if _is_placeholder_text(milestone_date_text):
        milestone_date_text = ""

    sections: list[str] = [
        "# Projektbericht",
        "",
        "## Allgemeine Angaben",
    ]
    if project_title_text:
        sections.append(f"- **Projekttitel:** {project_title_text}")
    if project_team_text:
        sections.append(f"- **Projektteam:** {project_team_text}")
    if date_text:
        sections.append(f"- **Datum:** {date_text}")

    if planned_lines:
        sections.extend(["", "## Was haben wir in dieser Woche geplant?", planned_lines])

    if achieved_lines:
        sections.extend(["", "## Was haben wir tatsächlich erreicht?", achieved_lines])

    if not_achieved_lines:
        sections.extend(["", "## Was haben wir nicht erreicht?", not_achieved_lines])

    if status_value:
        sections.extend(["", "## Projektstatus", f"**Wir sind:** {status_value}"])

    if delay_lines:
        sections.extend(["", "## Bei Verzug: Gegenmaßnahmen", delay_lines])

    if project_risk_table:
        sections.extend(["", "## Projektrisiko", project_risk_table])

    if task_risk_table:
        sections.extend(["", "## Aufgabenrisiko", task_risk_table])

    if milestone_text or milestone_date_text:
        sections.extend(["", "## Nächster Meilenstein"])
        if milestone_text:
            sections.append(f"- **Bezeichnung:** {milestone_text}")
        if milestone_date_text:
            sections.append(f"- **Geplantes Datum:** {milestone_date_text}")

    return "\n".join(sections) + "\n"
