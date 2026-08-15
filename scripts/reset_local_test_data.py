#!/usr/bin/env python3
"""Remove FlowNote runtime, smoke-test, and generated test artifacts safely.

The command is a dry run unless ``--apply`` is provided. It deliberately keeps
source tests, virtual environments, environment files, and the two tracked
``.gitkeep`` placeholders used by the API data directories.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_MARKERS = (
    Path(".gitignore"),
    Path("services/api/pyproject.toml"),
    Path("apps/windows/src/FlowNote.Windows.Core"),
    Path("apps/android/settings.gradle"),
)

# These trees contain only locally generated runtime data or test/build output.
REMOVE_TREES = (
    Path("data"),
    Path("Data"),
    Path("tmp"),
    Path("temp"),
    Path("artifacts"),
    Path("_workspace"),
    Path("storage"),
    Path("smoke-output"),
    Path("smoke-results"),
    Path("test-output"),
    Path("test-results"),
    Path("apps/windows/src/FlowNote.Windows.App/Data"),
    Path("apps/android/.gradle"),
    Path("apps/android/build"),
    Path("apps/android/app/build"),
    Path(".pytest_cache"),
    Path(".ruff_cache"),
    Path("htmlcov"),
)

# The directories themselves and their tracked placeholders must remain.
CLEAR_CONTENTS_EXCEPT_GITKEEP = (
    Path("services/api/data"),
    Path("services/api/storage"),
)

# Build/test caches can occur below several projects. Search only these roots.
GENERATED_DIRECTORY_NAMES = {"__pycache__", "bin", "obj", "TestResults"}
GENERATED_SEARCH_ROOTS = (
    Path("scripts"),
    Path("services/api/app"),
    Path("services/api/tests"),
    Path("apps/windows/src"),
)
GENERATED_FILES = (
    Path(".coverage"),
    Path("services/api/.coverage"),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "FlowNote 로컬 DB, storage, 스모크 증거, 테스트 결과와 빌드 캐시를 "
            "초기화합니다. 기본 동작은 삭제 대상만 보여주는 dry-run입니다."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="검증된 대상에 실제 삭제를 적용합니다.",
    )
    return parser.parse_args(argv)


def assert_repository_root(root: Path) -> None:
    missing = [str(marker) for marker in REQUIRED_MARKERS if not (root / marker).exists()]
    if missing:
        raise RuntimeError(
            "FlowNote 저장소 루트를 확인할 수 없습니다. 누락된 표식: " + ", ".join(missing)
        )


def assert_safe_target(root: Path, target: Path) -> None:
    resolved_root = root.resolve()
    resolved_target = target.resolve(strict=False)
    if resolved_target == resolved_root or resolved_root not in resolved_target.parents:
        raise RuntimeError(f"저장소 밖 또는 저장소 루트 삭제를 거부합니다: {target}")
    if ".git" in target.relative_to(root).parts:
        raise RuntimeError(f"Git 메타데이터 삭제를 거부합니다: {target}")


def add_existing_target(targets: dict[str, Path], root: Path, target: Path) -> None:
    if not target.exists() and not target.is_symlink():
        return
    assert_safe_target(root, target)
    key = str(target.resolve(strict=False)).casefold()
    targets.setdefault(key, target)


def collect_targets(root: Path) -> tuple[list[Path], list[Path]]:
    remove_targets: dict[str, Path] = {}
    for relative in REMOVE_TREES:
        add_existing_target(remove_targets, root, root / relative)

    for relative in GENERATED_SEARCH_ROOTS:
        search_root = root / relative
        if not search_root.exists():
            continue
        for candidate in search_root.rglob("*"):
            if candidate.is_dir() and candidate.name in GENERATED_DIRECTORY_NAMES:
                add_existing_target(remove_targets, root, candidate)

    for relative in GENERATED_FILES:
        add_existing_target(remove_targets, root, root / relative)

    clear_directories: list[Path] = []
    for relative in CLEAR_CONTENTS_EXCEPT_GITKEEP:
        directory = root / relative
        if directory.exists():
            assert_safe_target(root, directory)
            clear_directories.append(directory)

    # Removing a parent makes its descendants redundant and keeps output concise.
    ordered = sorted(remove_targets.values(), key=lambda path: len(path.parts))
    compact: list[Path] = []
    for candidate in ordered:
        resolved = candidate.resolve(strict=False)
        if any(parent.resolve(strict=False) in resolved.parents for parent in compact):
            continue
        compact.append(candidate)
    return compact, clear_directories


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
        return
    if path.is_dir():
        shutil.rmtree(path)


def clear_except_gitkeep(directory: Path, *, apply: bool) -> list[Path]:
    removed: list[Path] = []
    for child in sorted(directory.iterdir(), key=lambda path: path.name):
        if child.name == ".gitkeep":
            continue
        removed.append(child)
        if apply:
            remove_path(child)
    return removed


def run(*, apply: bool, root: Path = REPOSITORY_ROOT) -> int:
    assert_repository_root(root)
    remove_targets, clear_directories = collect_targets(root)
    content_targets: list[Path] = []
    for directory in clear_directories:
        content_targets.extend(clear_except_gitkeep(directory, apply=False))

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode}] FlowNote 로컬 테스트 데이터 초기화")
    for target in [*remove_targets, *content_targets]:
        print(f"- {target.relative_to(root)}")

    if not remove_targets and not content_targets:
        print("초기화할 로컬 테스트 데이터나 생성 산출물이 없습니다.")
        return 0

    if not apply:
        print("실제 삭제는 --apply를 붙여 실행하세요.")
        return 0

    for target in remove_targets:
        remove_path(target)
    for directory in clear_directories:
        clear_except_gitkeep(directory, apply=True)

    print(
        f"초기화 완료: 경로 {len(remove_targets) + len(content_targets)}개를 정리했습니다. "
        "소스 테스트, .env, 가상환경과 .gitkeep은 보존했습니다."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(apply=args.apply)
    except (OSError, RuntimeError) as error:
        print(f"초기화 실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
