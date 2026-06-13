# README Claim Matrix

| README claim | Evidence in repo | Verification command | Status |
| --- | --- | --- | --- |
| `lexintake init` creates workspace folders/config | `src/lexintake/cli.py`, `tests/test_cli.py` | `python -m pytest` | Implemented; tests passing locally 2026-06-13 |
| `lexintake run` processes dropped mail into review artifacts | `src/lexintake/pipeline.py`, `tests/test_pipeline.py` | `python -m pytest` | Implemented for tested fixtures |
| Offline Stages 2-5 do not require API keys with stub/default paths | `src/lexintake/providers/`, tests | `python -m pytest` | Implemented for tested converter path |
| Stage 1 browser export supports model providers | `src/lexintake/providers/`, `docs/PROVIDERS.md` | `provider-specific manual setup` | Optional; requires credentials and supervision |

Last local test evidence: `.venv/bin/python -m pytest` produced `36 passed in 2.42s` on 2026-06-13 in this workspace.
