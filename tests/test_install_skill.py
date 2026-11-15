"""Test cho utd install-skill: kiểm nguồn, không ghi đè, dry-run."""

import json
from pathlib import Path

import pytest

from utd.cli import EXIT_PASS, main
from utd.install_skill import (
    InstallError,
    install_skill,
    skill_source,
    validate_source,
)


def test_validate_source_passes():
    validate_source()  # không ném


def test_validate_source_rejects_missing_skill_md(tmp_path):
    empty = tmp_path / "src"
    empty.mkdir()
    with pytest.raises(InstallError) as excinfo:
        validate_source(empty)
    assert "SKILL.md" in str(excinfo.value)


def test_validate_source_rejects_missing_frontmatter(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("# No frontmatter\n", encoding="utf-8")

    with pytest.raises(InstallError) as excinfo:
        validate_source(src)
    assert "frontmatter" in str(excinfo.value)


def test_validate_source_rejects_missing_allowed_tools(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")

    with pytest.raises(InstallError) as excinfo:
        validate_source(src)
    assert "allowed-tools" in str(excinfo.value)


def test_install_creates_tree(tmp_path):
    result = install_skill(target=tmp_path / "skill")

    assert (tmp_path / "skill" / "SKILL.md").exists()
    assert (tmp_path / "skill" / "references" / "gate-rationale.md").exists()
    assert (tmp_path / "skill" / "assets" / "example_api_spec.json").exists()
    assert len(result.written) >= 6


def test_install_refuses_without_force(tmp_path):
    target = tmp_path / "skill"
    install_skill(target=target)

    with pytest.raises(InstallError) as excinfo:
        install_skill(target=target)
    assert "đã tồn tại" in str(excinfo.value)


def test_install_force_overwrites(tmp_path):
    target = tmp_path / "skill"
    install_skill(target=target)
    (target / "SKILL.md").write_text("rác", encoding="utf-8")

    install_skill(target=target, force=True)
    assert (target / "SKILL.md").read_text(encoding="utf-8").startswith("---")


def test_dry_run_writes_nothing(tmp_path):
    target = tmp_path / "skill"
    result = install_skill(target=target, dry_run=True)

    assert result.dry_run is True
    assert result.written
    assert not target.exists()


def test_cli_install_skill_dry_run(tmp_path):
    code = main(["install-skill", "--target", str(tmp_path / "s"), "--dry-run"])
    assert code == EXIT_PASS
    assert not (tmp_path / "s").exists()


def test_cli_install_skill_real(tmp_path):
    code = main(["install-skill", "--target", str(tmp_path / "s")])
    assert code == EXIT_PASS
    assert (tmp_path / "s" / "SKILL.md").exists()


def test_cli_install_skill_help_lists_flags():
    import argparse

    from utd.cli import build_parser

    parser = build_parser()
    install_parser = None
    for action in parser._subparsers._group_actions:
        if "install-skill" in action.choices:
            install_parser = action.choices["install-skill"]
    assert install_parser is not None
    flags = {opt for action in install_parser._actions for opt in action.option_strings}
    assert {"--target", "--force", "--dry-run"} <= flags


def test_skill_source_resolves():
    source = skill_source()
    assert (source / "SKILL.md").is_file()
