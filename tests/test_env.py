"""Reading a `.env` file.

The load bearing claim is the precedence one: a value already in the environment
must survive the file, because that is what lets one run override a setting without
editing anything. Everything else here guards the parsing of lines people actually
write, including the ones they write wrongly.
"""

from __future__ import annotations

from wastatus import env


def test_a_missing_file_is_normal_and_not_an_error(tmp_path):
    assert env.load(tmp_path / "nothing-here") == []


def test_a_setting_in_the_file_reaches_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("WASTATUS_PROXY", raising=False)
    file = tmp_path / ".env"
    file.write_text("WASTATUS_PROXY=http://127.0.0.1:8080\n")

    assert env.load(file) == ["WASTATUS_PROXY"]

    import os
    assert os.environ["WASTATUS_PROXY"] == "http://127.0.0.1:8080"


def test_the_environment_wins_over_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("WASTATUS_PROXY", "already set")
    file = tmp_path / ".env"
    file.write_text("WASTATUS_PROXY=from the file\n")

    assert env.load(file) == []

    import os
    assert os.environ["WASTATUS_PROXY"] == "already set"


def test_comments_blank_lines_and_export_are_all_understood(tmp_path, monkeypatch):
    for name in ("WASTATUS_A", "WASTATUS_B", "WASTATUS_C"):
        monkeypatch.delenv(name, raising=False)
    file = tmp_path / ".env"
    file.write_text(
        "# a comment\n"
        "\n"
        "WASTATUS_A=one\n"
        "   export WASTATUS_B=two\n"
        "  WASTATUS_C = three  \n"
    )

    assert env.load(file) == ["WASTATUS_A", "WASTATUS_B", "WASTATUS_C"]

    import os
    assert os.environ["WASTATUS_C"] == "three"


def test_quotes_are_how_a_value_keeps_its_spaces(tmp_path, monkeypatch):
    monkeypatch.delenv("WASTATUS_COOKIES_FROM_BROWSER", raising=False)
    file = tmp_path / ".env"
    file.write_text('WASTATUS_COOKIES_FROM_BROWSER="chrome:Profile 1"\n')

    env.load(file)

    import os
    assert os.environ["WASTATUS_COOKIES_FROM_BROWSER"] == "chrome:Profile 1"


def test_everything_after_the_first_equals_is_the_value(tmp_path, monkeypatch):
    """No inline comments, so a value never has to be escaped."""
    monkeypatch.delenv("WASTATUS_PROXY", raising=False)
    file = tmp_path / ".env"
    file.write_text("WASTATUS_PROXY=http://user:pa=ss@host:1080 # not a comment\n")

    env.load(file)

    import os
    assert os.environ["WASTATUS_PROXY"] == "http://user:pa=ss@host:1080 # not a comment"


def test_a_line_that_is_not_a_setting_is_skipped_rather_than_fatal(tmp_path, monkeypatch):
    monkeypatch.delenv("WASTATUS_A", raising=False)
    file = tmp_path / ".env"
    file.write_text("this is not a setting\n=novalue\nWASTATUS_A=kept\n")

    assert env.load(file) == ["WASTATUS_A"]


def test_the_override_points_at_another_file(tmp_path, monkeypatch):
    monkeypatch.delenv("WASTATUS_A", raising=False)
    elsewhere = tmp_path / "somewhere.env"
    elsewhere.write_text("WASTATUS_A=found\n")
    monkeypatch.setenv(env.OVERRIDE, str(elsewhere))

    assert env.load() == ["WASTATUS_A"]


def test_the_example_names_every_setting_the_code_reads():
    """A public repository's `.env.example` is a promise, so it is checked."""
    import re
    from pathlib import Path

    root = Path(env.__file__).resolve().parent.parent
    example = (root / ".env.example").read_text()
    named = set(re.findall(r"#?(WASTATUS_[A-Z_]+)=", example))

    read = set()
    for source in (root / "wastatus").glob("*.py"):
        read |= set(re.findall(r"WASTATUS_[A-Z_]+", source.read_text()))

    assert named == read
