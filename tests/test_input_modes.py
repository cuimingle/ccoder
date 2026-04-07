"""Tests for input mode detection and prefix handling."""
import pytest

from app.input_modes import InputMode, detect_mode, strip_mode_prefix, prepend_mode_prefix, is_mode_character


class TestDetectMode:
    def test_bash_mode(self):
        assert detect_mode("!ls") == InputMode.BASH

    def test_bash_mode_with_space(self):
        assert detect_mode("!git status") == InputMode.BASH

    def test_bash_mode_just_bang(self):
        assert detect_mode("!") == InputMode.BASH

    def test_prompt_mode_normal(self):
        assert detect_mode("hello world") == InputMode.PROMPT

    def test_prompt_mode_slash_command(self):
        assert detect_mode("/help") == InputMode.PROMPT

    def test_prompt_mode_empty(self):
        assert detect_mode("") == InputMode.PROMPT

    def test_bash_mode_with_leading_space(self):
        assert detect_mode("  !echo hello") == InputMode.BASH


class TestStripModePrefix:
    def test_strip_bash(self):
        assert strip_mode_prefix("!git status", InputMode.BASH) == "git status"

    def test_strip_bash_no_space(self):
        assert strip_mode_prefix("!ls", InputMode.BASH) == "ls"

    def test_strip_prompt_noop(self):
        assert strip_mode_prefix("hello", InputMode.PROMPT) == "hello"

    def test_strip_bash_just_bang(self):
        assert strip_mode_prefix("!", InputMode.BASH) == ""


class TestPrependModePrefix:
    def test_prepend_bash(self):
        assert prepend_mode_prefix("ls", InputMode.BASH) == "!ls"

    def test_prepend_prompt_strips_bang(self):
        assert prepend_mode_prefix("!ls", InputMode.PROMPT) == "ls"

    def test_prepend_bash_no_double(self):
        assert prepend_mode_prefix("!ls", InputMode.BASH) == "!ls"


class TestIsModeCharacter:
    def test_just_bang(self):
        assert is_mode_character("!") is True

    def test_bang_with_space(self):
        assert is_mode_character(" ! ") is True

    def test_not_mode_character(self):
        assert is_mode_character("hello") is False

    def test_bang_with_command(self):
        assert is_mode_character("!ls") is False
