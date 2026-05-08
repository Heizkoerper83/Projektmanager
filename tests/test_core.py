from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from pmtool import core


class CoreFlowsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = core.DB_PATH
        core.DB_PATH = Path(self.temp_dir.name) / "test_app.db"
        core.init_db()

    def tearDown(self) -> None:
        core.clear_current_principal()
        core.DB_PATH = self.old_db_path
        self.temp_dir.cleanup()

    def test_status_aliases_are_normalized(self) -> None:
        task_id = core.add_task("Alias Task", status="offen", return_id=True)
        task = core.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task["status"], "open")

        in_progress = core.list_tasks(status="in_bearbeitung")
        self.assertEqual(len(in_progress), 0)

        open_tasks = core.list_tasks(status="open")
        self.assertEqual(len(open_tasks), 1)
        self.assertEqual(open_tasks[0]["id"], task_id)

    def test_task_filters_for_due_tag_context_energy_and_blocked(self) -> None:
        today = date.today()
        core.add_task(
            "Heute Alpha",
            due_date=today.isoformat(),
            tags="alpha",
            context="home",
            energy_level="low",
        )
        core.add_task(
            "Blocked High",
            status="blocked",
            due_date=(today + timedelta(days=2)).isoformat(),
            tags="beta",
            context="office",
            energy_level="high",
        )
        core.add_task(
            "Overdue Alpha",
            due_date=(today - timedelta(days=1)).isoformat(),
            tags="alpha,beta",
            context="office",
            energy_level="medium",
        )
        core.add_task(
            "Done Overdue",
            status="done",
            due_date=(today - timedelta(days=3)).isoformat(),
            tags="archive",
            context="home",
        )

        overdue_titles = {row["title"] for row in core.list_tasks(due_filter="overdue")}
        self.assertIn("Overdue Alpha", overdue_titles)
        self.assertNotIn("Done Overdue", overdue_titles)

        blocked_titles = {row["title"] for row in core.list_tasks(due_filter="blocked")}
        self.assertEqual(blocked_titles, {"Blocked High"})

        alpha_titles = {row["title"] for row in core.list_tasks(tag="alpha")}
        self.assertEqual(alpha_titles, {"Heute Alpha", "Overdue Alpha"})

        office_titles = {row["title"] for row in core.list_tasks(context="office")}
        self.assertEqual(office_titles, {"Blocked High", "Overdue Alpha"})

        high_energy_titles = {row["title"] for row in core.list_tasks(energy_level="hoch")}
        self.assertEqual(high_energy_titles, {"Blocked High"})

    def test_template_flow_creates_task_with_offset_and_normalized_fields(self) -> None:
        core.add_project("Template Project")
        project_id = core.list_projects()[0]["id"]

        core.add_template(
            "Weekly Ops",
            title="Review Weekly",
            project_id=project_id,
            status="in_bearbeitung",
            due_offset_days=3,
            energy_level="mittel",
            tags="Alpha, alpha, BETA",
            recurrence_days=7,
        )
        template = core.list_templates()[0]

        task_id = core.create_task_from_template(template["id"])
        task = core.get_task(task_id)

        self.assertIsNotNone(task)
        self.assertEqual(task["title"], "Review Weekly")
        self.assertEqual(task["project_id"], project_id)
        self.assertEqual(task["status"], "in_progress")
        self.assertEqual(task["energy_level"], "medium")
        self.assertEqual(task["tags"], "alpha,beta")
        self.assertEqual(task["recurrence_days"], 7)
        self.assertEqual(task["due_date"], (date.today() + timedelta(days=3)).isoformat())

    def test_completing_recurring_task_spawns_follow_up(self) -> None:
        today = date.today().isoformat()
        task_id = core.add_task(
            "Recurring Standup",
            due_date=today,
            recurrence_days=2,
            return_id=True,
        )

        core.complete_task(task_id)

        matching = [row for row in core.list_tasks(search="Standup Recurring") if row["title"] == "Recurring Standup"]
        self.assertEqual(len(matching), 2)

        done_count = sum(1 for row in matching if row["status"] == "done")
        open_rows = [row for row in matching if row["status"] == "open"]
        self.assertEqual(done_count, 1)
        self.assertEqual(len(open_rows), 1)
        self.assertEqual(open_rows[0]["due_date"], (date.today() + timedelta(days=2)).isoformat())

    def test_search_accepts_special_characters(self) -> None:
        core.add_task("C++ Build", return_id=True)
        core.add_task("Node.js Update", return_id=True)

        cpp_matches = [row for row in core.list_tasks(search="C++") if row["title"] == "C++ Build"]
        node_matches = [row for row in core.list_tasks(search="Node.js") if row["title"] == "Node.js Update"]

        self.assertEqual(len(cpp_matches), 1)
        self.assertEqual(len(node_matches), 1)

    def test_project_and_task_risk_fields_are_saved(self) -> None:
        core.add_project(
            "Risk Project",
            risk="Lieferverzug bei Bauteilen",
            risk_probability=4,
            risk_impact=2,
            risk_countermeasure="Zweitlieferant aufbauen",
        )
        project = core.list_projects()[0]
        self.assertEqual(project["risk"], "Lieferverzug bei Bauteilen")
        self.assertEqual(project["risk_probability"], 4)
        self.assertEqual(project["risk_impact"], 2)
        self.assertEqual(project["risk_countermeasure"], "Zweitlieferant aufbauen")

        task_id = core.add_task(
            "PCB prüfen",
            project_id=project["id"],
            risk="Bestückungsfehler",
            risk_probability=5,
            risk_impact=1,
            risk_countermeasure="Peer-Review vor Fertigung",
            return_id=True,
        )
        task = core.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task["risk"], "Bestückungsfehler")
        self.assertEqual(task["risk_probability"], 5)
        self.assertEqual(task["risk_impact"], 1)
        self.assertEqual(task["risk_countermeasure"], "Peer-Review vor Fertigung")

        core.update_task(task_id, risk_probability=2, risk_impact=3)
        updated = core.get_task(task_id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["risk_probability"], 2)
        self.assertEqual(updated["risk_impact"], 3)

    def test_weekly_report_renders_risk_tables(self) -> None:
        markdown = core.build_weekly_project_report_markdown(
            project_title="Pico Board",
            project_team="Florian, Max",
            project_risks=[
                {
                    "risk": "Lieferengpass",
                    "probability": "4/5 (hoch)",
                    "impact": "3/5 (mittel)",
                    "countermeasure": "Zweitquelle aktivieren",
                }
            ],
            task_risks=[
                {
                    "risk": "PCB prüfen: Bestückungsfehler",
                    "probability": "5/5 (sehr hoch)",
                    "impact": "2/5 (gering)",
                    "countermeasure": "Peer-Review vor Fertigung",
                }
            ],
        )

        self.assertIn("## Projektrisiko", markdown)
        self.assertIn("- **Projekttitel:** Pico Board", markdown)
        self.assertIn("- **Projektteam:** Florian, Max", markdown)
        self.assertIn("| Risiko | Wahrscheinlichkeit | Ausmaß | Gegenmaßnahme |", markdown)
        self.assertIn("Lieferengpass", markdown)
        self.assertIn("## Aufgabenrisiko", markdown)
        self.assertIn("PCB prüfen: Bestückungsfehler", markdown)

    def test_weekly_report_omits_placeholders_and_empty_sections(self) -> None:
        markdown = core.build_weekly_project_report_markdown(
            planned_items=[],
            achieved_items=["[Platzhalter: Ziel]"],
            not_achieved_items=None,
            status_text="",
            delay_measures=["", ""],
            project_risks=[],
            task_risks=[],
            next_milestone="",
            next_milestone_date="",
        )

        self.assertNotIn("[Platzhalter:", markdown)
        self.assertNotIn("## Was haben wir tatsächlich erreicht?", markdown)
        self.assertNotIn("## Bei Verzug: Gegenmaßnahmen", markdown)
        self.assertNotIn("## Projektrisiko", markdown)
        self.assertNotIn("## Aufgabenrisiko", markdown)
        self.assertNotIn("## Nächster Meilenstein", markdown)

    def test_account_bound_projects_and_sharing_visibility(self) -> None:
        core.set_current_principal({"name": "alice", "role": "editor"})
        core.add_project("Alice Project")
        alice_project_id = core.list_projects()[0]["id"]
        core.add_task("Alice Task", project_id=alice_project_id)

        core.set_current_principal({"name": "bob", "role": "editor"})
        core.add_project("Bob Project")
        bob_project_id = core.list_projects()[0]["id"]
        core.add_task("Bob Task", project_id=bob_project_id)

        bob_visible_before = {row["name"] for row in core.list_projects()}
        self.assertEqual(bob_visible_before, {"Bob Project"})

        core.set_current_principal({"name": "alice", "role": "editor"})
        core.share_project(alice_project_id, "bob")

        core.set_current_principal({"name": "bob", "role": "editor"})
        bob_visible_after = {row["name"] for row in core.list_projects()}
        self.assertEqual(bob_visible_after, {"Bob Project", "Alice Project"})

        alice_tasks_for_bob = {row["title"] for row in core.list_tasks(project_id=alice_project_id, include_done=True)}
        self.assertIn("Alice Task", alice_tasks_for_bob)

        core.update_project(alice_project_id, goal="Mit Bob geteilt")
        core.set_current_principal({"name": "alice", "role": "editor"})
        shared_project = next(row for row in core.list_projects() if row["id"] == alice_project_id)
        self.assertEqual(shared_project["goal"], "Mit Bob geteilt")

    def test_reader_cannot_modify_project_data(self) -> None:
        core.set_current_principal({"name": "alice", "role": "editor"})
        core.add_project("ReadOnly Project")
        project_id = core.list_projects()[0]["id"]

        core.set_current_principal({"name": "alice", "role": "reader"})
        with self.assertRaises(ValueError):
            core.update_project(project_id, goal="Nicht erlaubt")

    def test_admin_can_modify_project_data(self) -> None:
        core.set_current_principal({"name": "alice", "role": "editor"})
        core.add_project("Admin Project")
        project_id = core.list_projects()[0]["id"]

        core.set_current_principal({"name": "alice", "role": "admin"})
        core.update_project(project_id, goal="Erlaubt")

        updated = next(row for row in core.list_projects() if row["id"] == project_id)
        self.assertEqual(updated["goal"], "Erlaubt")


if __name__ == "__main__":
    unittest.main()
