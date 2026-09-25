# {{PROJECT_TITLE}}

A conversational WebAppKit prototype. The assistant panel answers questions
about the datasets selected in the viewer, so replies stay grounded in the
session's images instead of free-floating text.

The generated project ships a placeholder reply function and no model
provider, so it runs without credentials. This is a prototype pattern built on
the existing custom workflow step, not a production chat surface.

## Run

Install the project dependencies:

```bash
uv sync
```

Start the application:

```bash
uv run python app.py
```

Then open <http://127.0.0.1:8000>, load an image, select it in the sidebar,
and ask a question on the **Assistant** step.

## Connect your model

Replace `answer()` in `conversation.py`:

```python
def answer(prompt: str, *, context: str) -> str:
    return my_client.complete(prompt, context=context, timeout=10)
```

The reply runs on the ImFusion owner thread, which every browser session
shares, so a slow call blocks the whole application rather than only the
caller's tab. Always pass a short timeout to network clients, and keep the
prompt small: send dataset descriptions such as `context`, not voxels.

`describe_selection()` builds that context from `app.selected_data`. Extend it
to include the metadata your model needs, such as intensity statistics,
orientation, or a rendered screenshot prepared beforehand on the owner thread.

## What this prototype does not do

- **No streaming.** A reply appears only after the handler returns. Token
  streaming would need new WebSocket messages and browser code.
- **One message at a time.** Sending runs as a session job, so no other
  operation can run in that tab until the reply arrives.
- **Single-line input.** The message field is a plain text parameter, and every
  keystroke resends the workflow state, so `visible_turns` in `conversation.py`
  caps how much transcript is transmitted. Press Enter to send; there is no
  separate Send button.
- **No persistence.** The transcript lives in the session. Closing the tab or
  clicking **New Conversation** discards it.

## Before using real data

The handler decides where prompts and context go. Sending patient data to a
third-party API is a deployment and compliance decision: WebAppKit has no
authentication, and sessions are not audited. Keep protected health
information out of prompts unless your deployment is approved for it.
