"""Tests for TUI components."""
from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from app.components.messages import Messages, _UserMessage, _AssistantMessage, _ToolCallRow, _SystemMessage
from app.components.prompt_input import PromptInput
from app.components.permission_prompt import PermissionPrompt
from app.types.permissions import PermissionResult


# --- Test app wrappers ---

class MessagesApp(App):
    def compose(self) -> ComposeResult:
        yield Messages(id="messages")


class PromptInputApp(App):
    def compose(self) -> ComposeResult:
        yield PromptInput(id="input")


class PermissionPromptApp(App):
    def compose(self) -> ComposeResult:
        yield PermissionPrompt(id="permission")


# --- Messages widget tests ---

class TestMessages:
    @pytest.mark.asyncio
    async def test_append_user_message(self):
        async with MessagesApp().run_test() as pilot:
            messages = pilot.app.query_one("#messages", Messages)
            messages.append_user("hello world")
            await pilot.pause()
            children = messages.query(_UserMessage)
            assert len(children) == 1

    @pytest.mark.asyncio
    async def test_streaming_assistant_chunks(self):
        async with MessagesApp().run_test() as pilot:
            messages = pilot.app.query_one("#messages", Messages)
            messages.append_assistant_chunk("Hello")
            messages.append_assistant_chunk(" world")
            await pilot.pause()
            children = messages.query(_AssistantMessage)
            assert len(children) == 1
            assert messages._assistant_buffer == "Hello world"

    @pytest.mark.asyncio
    async def test_finalize_assistant(self):
        async with MessagesApp().run_test() as pilot:
            messages = pilot.app.query_one("#messages", Messages)
            messages.append_assistant_chunk("done")
            messages.finalize_assistant()
            assert messages._assistant_widget is None
            assert messages._assistant_buffer == ""

    @pytest.mark.asyncio
    async def test_append_tool_call(self):
        async with MessagesApp().run_test() as pilot:
            messages = pilot.app.query_one("#messages", Messages)
            messages.append_tool_call("Bash", {"command": "ls"})
            await pilot.pause()
            children = messages.query(_ToolCallRow)
            assert len(children) == 1

    @pytest.mark.asyncio
    async def test_append_system(self):
        async with MessagesApp().run_test() as pilot:
            messages = pilot.app.query_one("#messages", Messages)
            messages.append_system("Session compacted.")
            await pilot.pause()
            children = messages.query(_SystemMessage)
            assert len(children) == 1

    @pytest.mark.asyncio
    async def test_clear_messages(self):
        async with MessagesApp().run_test() as pilot:
            messages = pilot.app.query_one("#messages", Messages)
            messages.append_user("a")
            messages.append_user("b")
            await pilot.pause()
            messages.clear_messages()
            await pilot.pause()
            assert len(messages.children) == 0


# --- PromptInput tests ---

class TestPromptInput:
    @pytest.mark.asyncio
    async def test_submit_posts_message(self):
        submitted_texts = []

        class TrackApp(App):
            def compose(self):
                yield PromptInput(id="input")

            def on_prompt_input_user_submitted(self, event: PromptInput.UserSubmitted):
                submitted_texts.append(event.text)

        async with TrackApp().run_test() as pilot:
            input_widget = pilot.app.query_one("#input", PromptInput)
            input_widget.value = "test message"
            await pilot.pause()
            # Simulate enter key press — triggers _on_key -> _submit
            await pilot.press("enter")
            await pilot.pause()
            assert submitted_texts == ["test message"]
            assert input_widget.value == ""

    @pytest.mark.asyncio
    async def test_empty_submit_ignored(self):
        submitted_texts = []

        class TrackApp(App):
            def compose(self):
                yield PromptInput(id="input")

            def on_prompt_input_user_submitted(self, event: PromptInput.UserSubmitted):
                submitted_texts.append(event.text)

        async with TrackApp().run_test() as pilot:
            await pilot.press("enter")
            await pilot.pause()
            assert submitted_texts == []

    @pytest.mark.asyncio
    async def test_history_stored(self):
        async with PromptInputApp().run_test() as pilot:
            input_widget = pilot.app.query_one("#input", PromptInput)
            input_widget.value = "first"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            input_widget.value = "second"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert input_widget._history == ["first", "second"]


# --- PermissionPrompt tests ---

class TestPermissionPrompt:
    @pytest.mark.asyncio
    async def test_show_and_hide(self):
        async with PermissionPromptApp().run_test() as pilot:
            prompt = pilot.app.query_one("#permission", PermissionPrompt)
            assert not prompt.has_class("visible")
            prompt.show_prompt("Bash", {"command": "rm -rf /"})
            assert prompt.has_class("visible")
            prompt.hide_prompt()
            assert not prompt.has_class("visible")

    @pytest.mark.asyncio
    async def test_allow_button_posts_resolved(self):
        results = []

        class TrackApp(App):
            def compose(self):
                yield PermissionPrompt(id="permission")

            def on_permission_prompt_resolved(self, event: PermissionPrompt.Resolved):
                results.append(event.result)

        async with TrackApp().run_test() as pilot:
            prompt = pilot.app.query_one("#permission", PermissionPrompt)
            prompt.show_prompt("Bash", {"command": "ls"})
            await pilot.pause()
            await pilot.click("#perm-allow")
            await pilot.pause()
            assert results == [PermissionResult.ALLOW]

    @pytest.mark.asyncio
    async def test_deny_button_posts_resolved(self):
        results = []

        class TrackApp(App):
            def compose(self):
                yield PermissionPrompt(id="permission")

            def on_permission_prompt_resolved(self, event: PermissionPrompt.Resolved):
                results.append(event.result)

        async with TrackApp().run_test() as pilot:
            prompt = pilot.app.query_one("#permission", PermissionPrompt)
            prompt.show_prompt("Bash", {"command": "rm /"})
            await pilot.pause()
            await pilot.click("#perm-deny")
            await pilot.pause()
            assert results == [PermissionResult.DENY]
