"""AskUserQuestionTool — present multiple choice questions to user."""
from __future__ import annotations
import json
from app.tool import BaseTool, ToolContext, ToolResult

ASK_USER_QUESTION_TOOL_CHIP_WIDTH = 12

_PROMPT = """\
Asks the user multiple choice questions to gather information, clarify ambiguity, \
understand preferences, make decisions or offer them choices.

Use this tool when you need to ask the user questions during execution. This allows you to:
1. Gather user preferences or requirements
2. Clarify ambiguous instructions
3. Get decisions on implementation choices as you work
4. Offer choices to the user about what direction to take.

Usage notes:
- Users will always be able to select "Other" to provide custom text input
- Use multiSelect: true to allow multiple answers to be selected for a question
- If you recommend a specific option, make that the first option in the list and add \
"(Recommended)" at the end of the label

Plan mode note: In plan mode, use this tool to clarify requirements or choose between \
approaches BEFORE finalizing your plan. Do NOT use this tool to ask "Is my plan ready?" \
or "Should I proceed?" - use ExitPlanMode for plan approval. IMPORTANT: Do not reference \
"the plan" in your questions (e.g., "Do you have feedback about the plan?", "Does the plan \
look good?") because the user cannot see the plan in the UI until you call ExitPlanMode. \
If you need plan approval, use ExitPlanMode instead.

Preview feature:
Use the optional `preview` field on options when presenting concrete artifacts that users \
need to visually compare:
- ASCII mockups of UI layouts or components
- Code snippets showing different implementations
- Diagram variations
- Configuration examples

Preview content is rendered as markdown in a monospace box. Multi-line text with newlines is \
supported. When any option has a preview, the UI switches to a side-by-side layout with a \
vertical option list on the left and preview on the right. Do not use previews for simple \
preference questions where labels and descriptions suffice. Note: previews are only supported \
for single-select questions (not multiSelect).\
"""


class AskUserQuestionTool(BaseTool):
    name = "AskUserQuestion"
    search_hint = "ask user question multiple choice clarify"

    input_schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": (
                                "The complete question to ask the user. Should be "
                                "self-contained and clearly worded."
                            ),
                        },
                        "header": {
                            "type": "string",
                            "description": (
                                f"Very short label displayed as a chip/tag "
                                f"(max {ASK_USER_QUESTION_TOOL_CHIP_WIDTH} chars)"
                            ),
                        },
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {
                                        "type": "string",
                                        "description": (
                                            "The display text for this option that the "
                                            "user will see and select. Should be concise "
                                            "(1-5 words) and clearly describe the choice."
                                        ),
                                    },
                                    "description": {
                                        "type": "string",
                                        "description": (
                                            "Explanation of what this option means or what "
                                            "will happen if chosen."
                                        ),
                                    },
                                    "preview": {
                                        "type": "string",
                                        "description": (
                                            "Optional preview content rendered when this "
                                            "option is focused."
                                        ),
                                    },
                                },
                                "required": ["label", "description"],
                            },
                            "minItems": 2,
                            "maxItems": 4,
                            "description": "The available choices for this question.",
                        },
                        "multiSelect": {
                            "type": "boolean",
                            "default": False,
                            "description": (
                                "Set to true to allow the user to select multiple "
                                "options instead of just one."
                            ),
                        },
                    },
                    "required": ["question", "header", "options"],
                },
                "minItems": 1,
                "maxItems": 4,
                "description": "Questions to ask the user (1-4 questions)",
            },
        },
        "required": ["questions"],
    }

    async def prompt(self) -> str:
        return _PROMPT

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrent_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, input_data: dict, context: ToolContext) -> ToolResult:
        questions = input_data["questions"]
        answers: dict[str, str | list[str]] = {}

        for q in questions:
            question_text = q["question"]
            options = q.get("options", [])
            multi = q.get("multiSelect", False)

            print(f"\n{question_text}")
            for i, opt in enumerate(options, 1):
                label = opt.get("label", str(opt))
                desc = opt.get("description", "")
                print(f"  {i}. {label}" + (f" \u2014 {desc}" if desc else ""))

            try:
                if multi:
                    raw = input(
                        f"Enter numbers (comma-separated, 1-{len(options)}): "
                    ).strip()
                    indices = [
                        int(x.strip()) - 1
                        for x in raw.split(",")
                        if x.strip().isdigit()
                    ]
                    selected = [
                        options[i].get("label", str(options[i]))
                        for i in indices
                        if 0 <= i < len(options)
                    ]
                    answers[question_text] = ", ".join(selected)
                else:
                    raw = input(f"Enter number (1-{len(options)}): ").strip()
                    idx = int(raw) - 1 if raw.isdigit() else 0
                    idx = max(0, min(idx, len(options) - 1))
                    answers[question_text] = options[idx].get(
                        "label", str(options[idx])
                    )
            except (EOFError, ValueError):
                # Non-interactive: default to first option
                answers[question_text] = (
                    options[0].get("label", str(options[0])) if options else ""
                )

        return ToolResult(
            content=json.dumps({"answers": answers}, ensure_ascii=False)
        )
