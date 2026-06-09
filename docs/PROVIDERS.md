# Computer-use providers (Stage 1 export)

Stage 1 drives a real browser session over your mailbox to export `.eml`
files into `01_mail_in/`. Three interchangeable providers; check readiness
any time with `lexintake doctor`.

| Provider | SDK | Key | Loop owner |
|---|---|---|---|
| `gemini` (default) | bundled with mail2md | `GEMINI_API_KEY` | mail2md's hardened agent |
| `openai` | `pip install lexintake[openai,browser]` | `OPENAI_API_KEY` | LexIntake (`openai_cua.py`) |
| `anthropic` | `pip install lexintake[anthropic,browser]` | `ANTHROPIC_API_KEY` | LexIntake (`anthropic_cua.py`) |

## Gemini (recommended)

Delegates to `mail2md.browser_agent.run_export` — host allow-lists per mail
provider, human confirmation gates on sensitive actions, bounded step count.

```powershell
$env:GEMINI_API_KEY = "..."
lexintake export C:\cases\lucerne --query "label:lucerne newer_than:1y" --execute
```

You log in yourself in the opened browser window; the agent never sees or
types your password.

## OpenAI / Anthropic

Both adapters share one Playwright executor (`providers/harness.py`) and are
built to the current API specs:

* **OpenAI** — Responses API `computer_use_preview` tool: the model returns
  `computer_call` items; we execute and reply with `computer_call_output`
  screenshots (`current_url` included so the API's own safety checks run).
* **Anthropic** — `computer_20251124` tool with the `computer-use-2025-11-24`
  beta header: the model emits `tool_use` blocks; we answer with
  `tool_result` image blocks.

Minimal launch recipe:

```python
from playwright.sync_api import sync_playwright
from lexintake.providers.harness import BrowserExecutor
from lexintake.providers.openai_cua import run_export_openai  # or anthropic_cua

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto("https://mail.google.com")
    input("Log in, open the target label, then press Enter... ")
    run_export_openai(
        "Export the 25 most recent messages in this view as .eml downloads.",
        BrowserExecutor(page),
    )
```

## Security posture

* Screenshots of your mailbox are sent to the chosen model provider — treat
  Stage 1 as a disclosure to that vendor and clear it with your firm first.
* Offline `lexintake run` never imports any of this; no key, no network.
* Login is always manual; profiles persist in `<workspace>/.browser-profile`.
