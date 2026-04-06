"""Tests for slash command dispatcher."""
from __future__ import annotations

from app.commands import is_command, parse_command


class TestParseCommand:
    def test_valid_command(self):
        result = parse_command("/compact")
        assert result == ("compact", "")

    def test_command_with_args(self):
        result = parse_command("/compact summary")
        assert result == ("compact", "summary")

    def test_not_a_command(self):
        assert parse_command("hello world") is None

    def test_empty_string(self):
        assert parse_command("") is None

    def test_slash_only(self):
        result = parse_command("/")
        assert result == ("", "")

    def test_command_with_whitespace(self):
        result = parse_command("  /help  ")
        assert result == ("help", "")

    def test_command_with_multiple_args(self):
        result = parse_command("/search foo bar baz")
        assert result == ("search", "foo bar baz")


class TestIsCommand:
    def test_is_command(self):
        assert is_command("/compact") is True

    def test_not_command(self):
        assert is_command("hello") is False

    def test_empty(self):
        assert is_command("") is False
