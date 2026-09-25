"""Conversation panel and model boundary for {{PROJECT_TITLE}}.

The assistant answers questions about the datasets selected in the viewer.
Replace :func:`answer` with a call to your own model.
"""

from imfusion_webappkit import (
    Alert,
    Button,
    CustomStep,
    Fields,
    StringParameter,
    Text,
)

VISIBLE_TURNS = 12
USER = "You"
ASSISTANT = "Assistant"


def answer(prompt: str, *, context: str) -> str:
    """Return one assistant reply.

    Replies are produced on the ImFusion owner thread, which every browser
    session shares, so a slow call blocks the whole application. Give any
    network client a short timeout, and describe datasets in ``context``
    instead of sending voxels.
    """
    return (
        "This starter replies without a model.\n\n"
        f"- Question: {prompt}\n"
        f"- Viewer context: {context}\n\n"
        "Replace `answer()` in `conversation.py` with your own model call."
    )


def describe_selection(app) -> str:
    """Summarize the selected datasets as text a model can consume."""
    selected = app.selected_data
    if not selected:
        return "No dataset is selected."
    return "; ".join(
        _describe(app.data_model.get_name(data) or "Unnamed dataset", data)
        for data in selected
    )


def _describe(name: str, data) -> str:
    details = []
    modality = getattr(data, "modality", None)
    if modality is not None:
        details.append(f"modality {getattr(modality, 'name', modality)}")
    image = _first_image(data)
    extents = tuple(
        getattr(image, axis, None) for axis in ("width", "height", "slices")
    )
    if all(isinstance(extent, int) for extent in extents):
        details.append("{}x{}x{} voxels".format(*extents))
    spacing = getattr(image, "spacing", None)
    if spacing is not None:
        millimeters = " x ".join(f"{float(value):.2f}" for value in spacing)
        details.append(f"spacing {millimeters} mm")
    return f"{name} ({', '.join(details)})" if details else name


def _first_image(data):
    """Return the first image of a set, or ``None`` for other data types."""
    try:
        return data[0]
    except (IndexError, KeyError, TypeError):
        return None


def _format_turn(speaker: str, message: str) -> str:
    """Render one turn. A left border sets the visitor's messages apart from
    the assistant's, so no "You" / "Assistant" label is needed."""
    if speaker != USER:
        return message
    return "\n".join(f"> {line}".rstrip() for line in message.splitlines())


class ConversationStep(CustomStep):
    """Chat panel grounded in the datasets selected in the viewer.

    The transcript belongs to one browser session. **New Conversation**
    clears it without affecting the rest of the workflow.
    """

    def __init__(
        self,
        handler=answer,
        title: str = "Assistant",
        step_id: str = "conversation",
        visible_turns: int = VISIBLE_TURNS,
    ):
        super().__init__(title, step_id=step_id)
        self.handler = handler
        self.visible_turns = visible_turns
        self._turns = []
        self._notice = None

    def reset_workflow_state(self) -> None:
        # Steps are shallow-copied for each session, so rebind the transcript
        # instead of clearing the list every session would otherwise share.
        super().reset_workflow_state()
        self._turns = []
        self._notice = None

    def body(self):
        elements = []
        if self._turns:
            elements.extend(
                Text(_format_turn(speaker, message))
                for speaker, message in self._turns[-self.visible_turns :]
            )
        else:
            elements.append(
                Text(
                    "Load an image, select it in the sidebar, then ask a "
                    "question about it."
                )
            )
        if self._notice is not None:
            elements.append(Alert(self._notice, "warning"))
        elements.append(
            Fields(
                [
                    StringParameter(
                        "prompt",
                        label="",
                        placeholder="Type your message here",
                        description="Ask about the selected datasets.",
                    )
                ],
                # Enter sends the message; there is no separate Send button.
                submit_action="send",
            )
        )
        elements.append(Button("new_conversation", "New Conversation"))
        return elements

    def on_action(self, action: str) -> None:
        if action == "new_conversation":
            self._turns = []
            self._notice = None
            return
        self._send(str(self.values["prompt"]).strip())

    def _send(self, prompt: str) -> None:
        if not prompt:
            self._notice = "Type a message before sending."
            return
        self._notice = None
        self._turns.append((USER, prompt))
        self._values = {**self._values, "prompt": ""}
        try:
            reply = self.handler(prompt, context=describe_selection(self.app))
        except Exception as exc:
            # A failed reply keeps the transcript instead of failing the job.
            self._notice = f"The assistant did not answer: {exc}"
            return
        if not reply.strip():
            self._notice = "The assistant returned an empty reply."
            return
        self._turns.append((ASSISTANT, reply))
