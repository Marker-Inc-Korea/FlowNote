"""Role-based UX baseline validation for FlowNote pilot evidence."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Callable


UX_ROLE_SCENARIOS = {
    "admin": (
        "WPF-DOCUMENT-FIELD-COMMENT",
        "WPF-HANDOVER-FOLLOW-UP",
        "WPF-REVIEW-REPORT",
    ),
    "line_foreman": (
        "WPF-DOCUMENT-FIELD-COMMENT",
        "WPF-HANDOVER-FOLLOW-UP",
        "WPF-REVIEW-REPORT-PERMISSION",
    ),
    "team_lead": (
        "WPF-DOCUMENT-FIELD-COMMENT",
        "WPF-HANDOVER-FOLLOW-UP",
        "WPF-REVIEW-REPORT-PERMISSION",
    ),
    "team_member": (
        "WPF-DOCUMENT-FIELD-COMMENT",
        "WPF-HANDOVER-FOLLOW-UP",
        "WPF-REVIEW-REPORT-PERMISSION",
    ),
}


def before_baseline_failures(
    run_root: Path,
    read_rows: Callable[[Path, str, str], tuple[list[dict[str, str]], list[str]]],
    parse_bool: Callable[[str | None], bool | None],
    check_evidence: Callable[[Path, object, str], list[str]],
) -> list[str]:
    rows, failures = read_rows(
        run_root,
        "scenario-results/role-ux-comparison.csv",
        "역할별 UX BEFORE 실측",
    )
    before_rows = [
        row
        for row in rows
        if (row.get("ui_phase") or "").strip().upper() == "BEFORE"
    ]
    required_pairs = {
        (role, scenario)
        for role, scenarios in UX_ROLE_SCENARIOS.items()
        for scenario in scenarios
    }
    observed_pairs: dict[tuple[str, str], list[dict[str, str]]] = {
        pair: [] for pair in required_pairs
    }
    observed_networks: set[str] = set()
    observed_gloves: set[str] = set()
    observed_one_hand: set[bool] = set()
    observed_positions: set[str] = set()

    for index, row in enumerate(before_rows, start=1):
        label = f"UX BEFORE 행 {index}"
        pair = (
            (row.get("role") or "").strip(),
            (row.get("scenario_id") or "").strip(),
        )
        if pair in observed_pairs:
            observed_pairs[pair].append(row)
        for field in (
            "comparison_id",
            "attempt_no",
            "participant_id",
            "condition_id",
            "network",
            "gloves",
            "one_hand",
            "terminal_position",
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
        ):
            if not (row.get(field) or "").strip():
                failures.append(f"{label}의 {field} 값이 없습니다.")

        network = (row.get("network") or "").strip().upper()
        gloves = (row.get("gloves") or "").strip().upper()
        one_hand = parse_bool(row.get("one_hand"))
        if network not in ("CONNECTED", "DISCONNECTED"):
            failures.append(f"{label}의 network는 CONNECTED/DISCONNECTED여야 합니다.")
        else:
            observed_networks.add(network)
        if gloves not in ("ON", "OFF"):
            failures.append(f"{label}의 gloves는 ON/OFF여야 합니다.")
        else:
            observed_gloves.add(gloves)
        if one_hand is None:
            failures.append(f"{label}의 one_hand 값이 올바르지 않습니다.")
        else:
            observed_one_hand.add(one_hand)
        for field in (
            "success",
            "source_preservation_understood",
            "next_action_understood",
            "critical_blocker",
        ):
            if parse_bool(row.get(field)) is None:
                failures.append(f"{label}의 {field} 값이 올바르지 않습니다.")
        try:
            values = (
                float((row.get("elapsed_seconds") or "").strip()),
                int((row.get("click_count") or "").strip()),
                int((row.get("screen_transitions") or "").strip()),
                int((row.get("help_request_count") or "").strip()),
                int((row.get("source_loss_count") or "").strip()),
                int((row.get("receipt_loss_count") or "").strip()),
                int((row.get("duplicate_creation_count") or "").strip()),
            )
            if min(values) < 0:
                raise ValueError
        except ValueError:
            failures.append(
                f"{label}의 시간·선택·화면 이동·도움 요청·유실·중복 값이 올바르지 않습니다."
            )
        failures.extend(
            check_evidence(
                run_root,
                [(row.get("screen_capture_evidence") or "").strip()],
                f"{label} 화면 증거",
            )
        )
        position = (row.get("terminal_position") or "").strip()
        if position:
            observed_positions.add(position)

    for (role, scenario), matching in sorted(observed_pairs.items()):
        if len(matching) < 2:
            failures.append(
                f"역할 {role}의 {scenario} BEFORE는 같은 참여자와 시나리오로 2회 이상 측정해야 합니다."
            )
            continue
        participants = {
            (row.get("participant_id") or "").strip() for row in matching
        }
        builds = {(row.get("ui_build") or "").strip() for row in matching}
        attempts = [(row.get("attempt_no") or "").strip() for row in matching]
        if len(participants) != 1 or "" in participants:
            failures.append(
                f"역할 {role}의 {scenario} BEFORE는 같은 익명 참여자로 측정해야 합니다."
            )
        if len(builds) != 1 or "" in builds:
            failures.append(
                f"역할 {role}의 {scenario} BEFORE는 하나의 UI build로 측정해야 합니다."
            )
        if len(attempts) != len(set(attempts)):
            failures.append(
                f"역할 {role}의 {scenario} BEFORE attempt_no가 중복됩니다."
            )

    if observed_networks != {"CONNECTED", "DISCONNECTED"}:
        failures.append("UX BEFORE에는 연결 상태와 단절 상태 관찰이 모두 필요합니다.")
    if observed_gloves != {"ON", "OFF"}:
        failures.append("UX BEFORE에는 장갑 착용과 미착용 관찰이 모두 필요합니다.")
    if observed_one_hand != {True, False}:
        failures.append("UX BEFORE에는 한 손 사용과 양손 사용 관찰이 모두 필요합니다.")
    if not observed_positions:
        failures.append("UX BEFORE에는 단말 거치 위치 기록이 필요합니다.")
    return failures


def revalidation_failures(
    run_root: Path,
    observations: list[dict[str, str]],
    items: list[dict[str, str]],
    read_rows: Callable[[Path, str, str], tuple[list[dict[str, str]], list[str]]],
    parse_bool: Callable[[str | None], bool | None],
    check_evidence: Callable[[Path, object, str], list[str]],
) -> list[str]:
    high_priority_items = [
        row
        for row in items
        if (row.get("decision") or "").strip() == "ACCEPTED"
        and (row.get("priority") or "").strip() in ("P0", "P1")
    ]
    if not high_priority_items:
        return []
    rows, failures = read_rows(
        run_root,
        "scenario-results/role-ux-comparison.csv",
        "P0/P1 UX 수정 전후 재검증",
    )
    observations_by_id = {
        (row.get("observation_id") or "").strip(): row for row in observations
    }
    comparisons: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        comparison_id = (row.get("comparison_id") or "").strip()
        if comparison_id:
            comparisons.setdefault(comparison_id, []).append(row)

    for item in high_priority_items:
        item_id = (item.get("item_id") or "").strip() or "식별자 없음"
        comparison_id = (item.get("comparison_id") or "").strip()
        development_cycle_id = (item.get("development_cycle_id") or "").strip()
        status = (item.get("status") or "").strip().upper()
        if not comparison_id or not development_cycle_id:
            failures.append(
                f"수용한 P0/P1 UX 개발 항목 {item_id}에 "
                "development_cycle_id와 comparison_id가 필요합니다."
            )
            continue
        if status not in ("VERIFIED", "CLOSED"):
            failures.append(
                f"수용한 P0/P1 UX 개발 항목 {item_id}의 status는 "
                "VERIFIED 또는 CLOSED여야 합니다."
            )
        matching = comparisons.get(comparison_id, [])
        if not matching:
            failures.append(
                f"수용한 P0/P1 UX 개발 항목 {item_id}의 "
                f"수정 전후 비교 {comparison_id}가 없습니다."
            )
            continue

        observation = observations_by_id.get(
            (item.get("observation_id") or "").strip(), {}
        )
        expected_role = (observation.get("role") or "").strip()
        expected_scenario = (observation.get("scenario_id") or "").strip()
        phases: dict[str, list[dict[str, str]]] = {"BEFORE": [], "AFTER": []}
        identities: set[tuple[str, str, str, str]] = set()
        builds: dict[str, set[str]] = {"BEFORE": set(), "AFTER": set()}
        attempt_keys: set[tuple[str, int]] = set()
        contexts: dict[str, dict[int, tuple[str, str, str, bool, str]]] = {
            phase: {} for phase in phases
        }
        numeric: dict[str, dict[str, list[float]]] = {
            phase: {
                "elapsed_seconds": [],
                "screen_transitions": [],
                "help_request_count": [],
            }
            for phase in phases
        }
        for index, row in enumerate(matching, start=1):
            label = f"UX 비교 {comparison_id} 행 {index}"
            phase = (row.get("ui_phase") or "").strip().upper()
            if phase not in phases:
                failures.append(f"{label}의 ui_phase는 BEFORE 또는 AFTER여야 합니다.")
                continue
            phases[phase].append(row)
            role = (row.get("role") or "").strip()
            participant = (row.get("participant_id") or "").strip()
            scenario = (row.get("scenario_id") or "").strip()
            cycle = (row.get("development_cycle_id") or "").strip()
            build = (row.get("ui_build") or "").strip()
            condition_id = (row.get("condition_id") or "").strip()
            network = (row.get("network") or "").strip().upper()
            gloves = (row.get("gloves") or "").strip().upper()
            one_hand = parse_bool(row.get("one_hand"))
            terminal_position = (row.get("terminal_position") or "").strip()
            if not all(
                (
                    role,
                    participant,
                    scenario,
                    cycle,
                    build,
                    condition_id,
                    terminal_position,
                )
            ):
                failures.append(
                    f"{label}의 역할·익명 참여자·시나리오·조건·거치 위치·"
                    "개발 주기·UI build가 모두 필요합니다."
                )
            if network not in ("CONNECTED", "DISCONNECTED"):
                failures.append(
                    f"{label}의 network는 CONNECTED/DISCONNECTED여야 합니다."
                )
            if gloves not in ("ON", "OFF"):
                failures.append(f"{label}의 gloves는 ON/OFF여야 합니다.")
            if one_hand is None:
                failures.append(f"{label}의 one_hand 값이 올바르지 않습니다.")
            identities.add((role, participant, scenario, cycle))
            if build:
                builds[phase].add(build)
            if role != expected_role or scenario != expected_scenario:
                failures.append(f"{label}가 원 관찰의 역할·시나리오와 다릅니다.")
            if cycle != development_cycle_id:
                failures.append(
                    f"{label}의 개발 주기가 UX 개발 항목 {item_id}와 다릅니다."
                )
            try:
                attempt_no = int((row.get("attempt_no") or "").strip())
                if attempt_no < 1 or (phase, attempt_no) in attempt_keys:
                    raise ValueError
            except ValueError:
                failures.append(
                    f"{label}의 attempt_no는 단계 안에서 "
                    "중복 없는 1 이상의 정수여야 합니다."
                )
            else:
                attempt_keys.add((phase, attempt_no))
                if (
                    condition_id
                    and network in ("CONNECTED", "DISCONNECTED")
                    and gloves in ("ON", "OFF")
                    and one_hand is not None
                    and terminal_position
                ):
                    contexts[phase][attempt_no] = (
                        condition_id,
                        network,
                        gloves,
                        one_hand,
                        terminal_position,
                    )
            if parse_bool(row.get("success")) is None:
                failures.append(f"{label}의 success 값이 올바르지 않습니다.")
            source_understood = parse_bool(row.get("source_preservation_understood"))
            next_action_understood = parse_bool(row.get("next_action_understood"))
            critical_blocker = parse_bool(row.get("critical_blocker"))
            for field, value in (
                ("source_preservation_understood", source_understood),
                ("next_action_understood", next_action_understood),
                ("critical_blocker", critical_blocker),
            ):
                if value is None:
                    failures.append(f"{label}의 {field} 값이 올바르지 않습니다.")
            try:
                elapsed = float((row.get("elapsed_seconds") or "").strip())
                click_count = int((row.get("click_count") or "").strip())
                transitions = int((row.get("screen_transitions") or "").strip())
                help_count = int((row.get("help_request_count") or "").strip())
                source_loss = int((row.get("source_loss_count") or "").strip())
                receipt_loss = int((row.get("receipt_loss_count") or "").strip())
                duplicates = int((row.get("duplicate_creation_count") or "").strip())
                if min(
                    elapsed,
                    click_count,
                    transitions,
                    help_count,
                    source_loss,
                    receipt_loss,
                    duplicates,
                ) < 0:
                    raise ValueError
            except ValueError:
                failures.append(
                    f"{label}의 시간·선택·화면 이동·도움 요청·"
                    "유실·중복 값이 올바르지 않습니다."
                )
            else:
                numeric[phase]["elapsed_seconds"].append(elapsed)
                numeric[phase]["screen_transitions"].append(float(transitions))
                numeric[phase]["help_request_count"].append(float(help_count))
                if phase == "AFTER" and any(
                    value != 0 for value in (source_loss, receipt_loss, duplicates)
                ):
                    failures.append(
                        f"{label}의 AFTER 원천 유실·처리 결과 유실·"
                        "중복 생성은 모두 0이어야 합니다."
                    )
            if phase == "AFTER" and (
                source_understood is not True or next_action_understood is not True
            ):
                failures.append(
                    f"{label}의 AFTER에서는 원천 보존 여부와 "
                    "다음 행동을 모두 이해해야 합니다."
                )
            if phase == "AFTER" and critical_blocker is not False:
                failures.append(f"{label}의 AFTER 치명적 blocker는 0이어야 합니다.")
            failures.extend(
                check_evidence(
                    run_root,
                    [(row.get("screen_capture_evidence") or "").strip()],
                    f"{label} 화면 증거",
                )
            )

        if len(identities) != 1:
            failures.append(
                f"UX 비교 {comparison_id}는 같은 역할·익명 참여자·시나리오·"
                "개발 주기로 수행해야 합니다."
            )
        for phase in ("BEFORE", "AFTER"):
            if len(phases[phase]) < 2:
                failures.append(
                    f"UX 비교 {comparison_id}의 {phase} 단계는 2회 이상 수행해야 합니다."
                )
            if len(builds[phase]) != 1:
                failures.append(
                    f"UX 비교 {comparison_id}의 {phase} 단계는 "
                    "하나의 UI build로 측정해야 합니다."
                )
        if builds["BEFORE"] & builds["AFTER"]:
            failures.append(
                f"UX 비교 {comparison_id}의 BEFORE와 AFTER UI build는 달라야 합니다."
            )
        if contexts["BEFORE"] != contexts["AFTER"]:
            failures.append(
                f"UX 비교 {comparison_id}의 BEFORE와 AFTER 조건·시도 번호가 다릅니다."
            )
        if phases["AFTER"] and any(
            parse_bool(row.get("success")) is not True for row in phases["AFTER"]
        ):
            failures.append(
                f"UX 비교 {comparison_id}의 AFTER 시도는 모두 성공해야 합니다."
            )
        for field, label in (
            ("elapsed_seconds", "중앙 완료 시간"),
            ("screen_transitions", "중앙 화면 이동 수"),
            ("help_request_count", "중앙 도움 요청 수"),
        ):
            before_values = numeric["BEFORE"][field]
            after_values = numeric["AFTER"][field]
            if (
                before_values
                and after_values
                and statistics.median(after_values)
                > statistics.median(before_values)
            ):
                failures.append(
                    f"UX 비교 {comparison_id}의 AFTER {label}이 BEFORE보다 나빠졌습니다."
                )
    return failures
