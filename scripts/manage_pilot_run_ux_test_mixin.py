from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("manage-pilot-run.py")
SPEC = importlib.util.spec_from_file_location("manage_pilot_run_ux", SCRIPT_PATH)
assert SPEC and SPEC.loader
manage_pilot_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage_pilot_run)


class ManagePilotRunUxTestMixin:
    def test_before_baseline_requires_all_roles_three_flows_and_context_split(
        self,
    ) -> None:
        rows = []
        comparison_no = 0
        for role, scenarios in manage_pilot_run.UX_ROLE_SCENARIOS.items():
            for scenario in scenarios:
                comparison_no += 1
                for attempt_no in (1, 2):
                    rows.append(
                        {
                            "comparison_id": f"BASELINE-{comparison_no:02}",
                            "development_cycle_id": "",
                            "attempt_no": attempt_no,
                            "role": role,
                            "participant_id": f"PARTICIPANT-{role}",
                            "scenario_id": scenario,
                            "condition_id": f"CONDITION-{attempt_no}",
                            "network": "CONNECTED" if attempt_no == 1 else "DISCONNECTED",
                            "gloves": "OFF" if attempt_no == 1 else "ON",
                            "one_hand": "FALSE" if attempt_no == 1 else "TRUE",
                            "terminal_position": "FIXED-STAND",
                            "ui_phase": "BEFORE",
                            "ui_build": "wpf-before",
                            "success": "TRUE",
                            "elapsed_seconds": 20,
                            "click_count": 5,
                            "screen_transitions": 4,
                            "help_request_count": 0,
                            "source_preservation_understood": "FALSE",
                            "next_action_understood": "FALSE",
                            "source_loss_count": 0,
                            "receipt_loss_count": 0,
                            "duplicate_creation_count": 0,
                            "critical_blocker": "FALSE",
                            "screen_capture_evidence": "proof.txt",
                            "notes": "same approved baseline",
                        }
                    )
        self.write_csv(
            "scenario-results/role-ux-comparison.csv", list(rows[0]), rows
        )

        self.assertEqual(
            [],
            manage_pilot_run.ux_before_baseline_csv_failures(self.run_root),
        )

        rows = [
            row
            for row in rows
            if not (
                row["role"] == "team_member"
                and row["scenario_id"] == "WPF-HANDOVER-FOLLOW-UP"
            )
        ]
        self.write_csv(
            "scenario-results/role-ux-comparison.csv", list(rows[0]), rows
        )
        failures = manage_pilot_run.ux_before_baseline_csv_failures(self.run_root)
        self.assertTrue(
            any(
                "team_member의 WPF-HANDOVER-FOLLOW-UP BEFORE" in failure
                for failure in failures
            )
        )

    def test_actionable_observations_convert_one_to_one_to_owned_items(self) -> None:
        observations_path = self.run_root / "observations" / "role-observations.csv"
        observations_path.parent.mkdir(parents=True)
        observation_fields = [
            "observation_id",
            "role",
            "scenario_id",
            "device_id",
            "location",
            "network",
            "gloves",
            "one_hand",
            "lighting",
            "terminal_position",
            "input_moment",
            "terminology_confusion",
            "button_confusion",
            "photo_capture",
            "short_memo",
            "signal_input",
            "actionable",
            "success",
            "elapsed_seconds",
            "retry_count",
            "help_request_count",
            "screen_transitions",
            "notes",
            "evidence",
        ]
        with observations_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=observation_fields)
            writer.writeheader()
            for index, role in enumerate(manage_pilot_run.REQUIRED_ROLES):
                writer.writerow(
                    {
                        "observation_id": f"OBS-{index}",
                        "role": role,
                        "scenario_id": manage_pilot_run.ROLE_SCENARIOS[role][0],
                        "device_id": "DEVICE-01",
                        "location": "LINE-01",
                        "network": "DISCONNECTED" if index == 0 else "CONNECTED",
                        "gloves": "ON" if index == 0 else "OFF",
                        "one_hand": "TRUE",
                        "lighting": "NORMAL",
                        "terminal_position": "FIXED-STAND",
                        "input_moment": "AFTER-TASK",
                        "terminology_confusion": "FALSE",
                        "button_confusion": "FALSE",
                        "photo_capture": "TRUE",
                        "short_memo": "TRUE",
                        "signal_input": "TRUE",
                        "actionable": "TRUE" if index == 0 else "FALSE",
                        "success": "TRUE",
                        "elapsed_seconds": "10",
                        "retry_count": "0",
                        "help_request_count": "0",
                        "screen_transitions": "2",
                        "notes": "anonymous observation",
                        "evidence": "proof.txt",
                    }
                )

        items_path = self.run_root / "observations" / "development-items.csv"
        item_fields = [
            "item_id",
            "observation_id",
            "decision",
            "decision_basis",
            "priority",
            "classification",
            "title",
            "acceptance_criteria",
            "owner",
            "due_date",
            "status",
            "evidence",
        ]
        with items_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=item_fields)
            writer.writeheader()
            for index, _role in enumerate(manage_pilot_run.REQUIRED_ROLES):
                writer.writerow(
                    {
                        "item_id": f"UX-{index:03}",
                        "observation_id": f"OBS-{index}",
                        "decision": "ACCEPTED" if index == 0 else "REJECTED",
                        "decision_basis": "익명 관찰 근거",
                        "priority": "P2" if index == 0 else "P3",
                        "classification": (
                            "common_product"
                            if index == 0
                            else "site_layout"
                        ),
                        "title": "장갑 입력 개선" if index == 0 else "현장별 선호 보존",
                        "acceptance_criteria": "같은 조건에서 첫 시도 성공",
                        "owner": "product-owner",
                        "due_date": "2026-08-31",
                        "status": "OPEN",
                        "evidence": "proof.txt",
                    }
                )
        expected = {
            "actionable_findings": 1,
            "converted_items": 4,
            "unconverted_actionable_findings": 0,
            "priorities": {"P0": 0, "P1": 0, "P2": 1, "P3": 3},
            "classifications": {
                "common_product": 1,
                "configuration_or_training": 0,
                "site_layout": 3,
            },
        }

        self.assertEqual([], manage_pilot_run.ux_csv_failures(self.run_root, expected))

    def test_accepted_p0_p1_requires_same_cycle_before_after_revalidation(
        self,
    ) -> None:
        observations = [
            {
                "observation_id": "OBS-P1",
                "role": "team_member",
                "scenario_id": "TEAM-MEMBER-HANDOVER",
            }
        ]
        items = [
            {
                "item_id": "UX-P1",
                "observation_id": "OBS-P1",
                "decision": "ACCEPTED",
                "priority": "P1",
                "status": "VERIFIED",
                "development_cycle_id": "CYCLE-20260727-01",
                "comparison_id": "COMPARE-P1",
            }
        ]
        comparison_path = (
            self.run_root / "scenario-results" / "role-ux-comparison.csv"
        )
        comparison_path.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "comparison_id",
            "development_cycle_id",
            "attempt_no",
            "role",
            "participant_id",
            "scenario_id",
            "condition_id",
            "network",
            "gloves",
            "one_hand",
            "terminal_position",
            "ui_phase",
            "ui_build",
            "success",
            "elapsed_seconds",
            "click_count",
            "screen_transitions",
            "help_request_count",
            "source_preservation_understood",
            "next_action_understood",
            "source_loss_count",
            "receipt_loss_count",
            "duplicate_creation_count",
            "critical_blocker",
            "screen_capture_evidence",
            "notes",
        ]
        with comparison_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for phase, build, elapsed, transitions, help_count in (
                ("BEFORE", "wpf-before", 20, 5, 1),
                ("AFTER", "wpf-after", 12, 3, 0),
            ):
                for attempt_no in (1, 2):
                    writer.writerow(
                        {
                            "comparison_id": "COMPARE-P1",
                            "development_cycle_id": "CYCLE-20260727-01",
                            "attempt_no": attempt_no,
                            "role": "team_member",
                            "participant_id": "PARTICIPANT-01",
                            "scenario_id": "TEAM-MEMBER-HANDOVER",
                            "condition_id": f"CONDITION-{attempt_no}",
                            "network": "CONNECTED" if attempt_no == 1 else "DISCONNECTED",
                            "gloves": "OFF" if attempt_no == 1 else "ON",
                            "one_hand": "FALSE" if attempt_no == 1 else "TRUE",
                            "terminal_position": "FIXED-STAND",
                            "ui_phase": phase,
                            "ui_build": build,
                            "success": "TRUE",
                            "elapsed_seconds": elapsed,
                            "click_count": 4,
                            "screen_transitions": transitions,
                            "help_request_count": help_count,
                            "source_preservation_understood": "TRUE" if phase == "AFTER" else "FALSE",
                            "next_action_understood": "TRUE" if phase == "AFTER" else "FALSE",
                            "source_loss_count": 0,
                            "receipt_loss_count": 0,
                            "duplicate_creation_count": 0,
                            "critical_blocker": "FALSE",
                            "screen_capture_evidence": "proof.txt",
                            "notes": "same approved scenario",
                        }
                    )

        self.assertEqual(
            [],
            manage_pilot_run.ux_revalidation_csv_failures(
                self.run_root, observations, items
            ),
        )

        items[0]["comparison_id"] = ""
        failures = manage_pilot_run.ux_revalidation_csv_failures(
            self.run_root, observations, items
        )
        self.assertTrue(
            any(
                "development_cycle_id와 comparison_id가 필요" in failure
                for failure in failures
            )
        )

    def test_p0_p1_revalidation_rejects_after_regression(self) -> None:
        observations = [
            {
                "observation_id": "OBS-P0",
                "role": "admin",
                "scenario_id": "ADMIN-REVIEW-REPORT",
            }
        ]
        items = [
            {
                "item_id": "UX-P0",
                "observation_id": "OBS-P0",
                "decision": "ACCEPTED",
                "priority": "P0",
                "status": "CLOSED",
                "development_cycle_id": "CYCLE-20260727-02",
                "comparison_id": "COMPARE-P0",
            }
        ]
        rows = []
        for phase, build, elapsed in (
            ("BEFORE", "wpf-before", 10),
            ("AFTER", "wpf-after", 11),
        ):
            for attempt_no in (1, 2):
                rows.append(
                    {
                        "comparison_id": "COMPARE-P0",
                        "development_cycle_id": "CYCLE-20260727-02",
                        "attempt_no": attempt_no,
                        "role": "admin",
                        "participant_id": "PARTICIPANT-ADMIN-01",
                        "scenario_id": "ADMIN-REVIEW-REPORT",
                        "condition_id": f"CONDITION-{attempt_no}",
                        "network": "CONNECTED" if attempt_no == 1 else "DISCONNECTED",
                        "gloves": "OFF" if attempt_no == 1 else "ON",
                        "one_hand": "FALSE" if attempt_no == 1 else "TRUE",
                        "terminal_position": "DESK-STAND",
                        "ui_phase": phase,
                        "ui_build": build,
                        "success": "TRUE",
                        "elapsed_seconds": elapsed,
                        "click_count": 4,
                        "screen_transitions": 3,
                        "help_request_count": 0,
                        "source_preservation_understood": "TRUE" if phase == "AFTER" else "FALSE",
                        "next_action_understood": "TRUE" if phase == "AFTER" else "FALSE",
                        "source_loss_count": 0,
                        "receipt_loss_count": 0,
                        "duplicate_creation_count": 0,
                        "critical_blocker": "FALSE",
                        "screen_capture_evidence": "proof.txt",
                        "notes": "same approved scenario",
                    }
                )
        self.write_csv(
            "scenario-results/role-ux-comparison.csv", list(rows[0]), rows
        )

        failures = manage_pilot_run.ux_revalidation_csv_failures(
            self.run_root, observations, items
        )

        self.assertTrue(
            any(
                "AFTER 중앙 완료 시간이 BEFORE보다 나빠졌습니다" in item
                for item in failures
            )
        )

        for row in rows:
            if row["ui_phase"] != "AFTER":
                continue
            row["elapsed_seconds"] = 9
            row["source_preservation_understood"] = "FALSE"
            row["next_action_understood"] = "FALSE"
            row["source_loss_count"] = 1
            row["receipt_loss_count"] = 1
            row["duplicate_creation_count"] = 1
            row["critical_blocker"] = "TRUE"
        rows[-1]["terminal_position"] = "DIFFERENT-STAND"
        self.write_csv(
            "scenario-results/role-ux-comparison.csv", list(rows[0]), rows
        )

        failures = manage_pilot_run.ux_revalidation_csv_failures(
            self.run_root, observations, items
        )
        self.assertTrue(any("유실·중복 생성은 모두 0" in item for item in failures))
        self.assertTrue(
            any("원천 보존 여부와 다음 행동을 모두 이해" in item for item in failures)
        )
        self.assertTrue(any("치명적 blocker는 0" in item for item in failures))
        self.assertTrue(any("조건·시도 번호가 다릅니다" in item for item in failures))
