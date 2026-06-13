"""LexIntake command line.

    lexintake init      WORKSPACE --notebook ID [--backend ...] [--provider ...]
    lexintake run       [WORKSPACE]            offline Stages 2-5
    lexintake export    [WORKSPACE] --query Q [--execute]   Stage 1 then 2-5
    lexintake status    [WORKSPACE]            tracked sources + last run
    lexintake doctor    [WORKSPACE]            environment + provider readiness

WORKSPACE defaults to the current directory, so the daily attorney loop is
just: drop exports into 01_mail_in, run ``lexintake run``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import CONFIG_NAME, LexConfig
from .providers import available_providers, get_capability


def _load(args) -> LexConfig:
    """Load configuration from the workspace, overlaid with CLI flags.
    
    This function ensures that CLI arguments take precedence over the saved
    configuration for the current run, without overwriting the stored file.
    """
    # Load base configuration from the lexintake.toml in the workspace
    cfg = LexConfig.load(Path(args.workspace))
    # CLI flags override the file for this run only (config stays authoritative).
    for attr in ("notebook", "backend", "provider"):
        value = getattr(args, attr, None)
        if value:
            setattr(cfg, attr, value)
    return cfg


def _print_report(report) -> None:
    print(f"\nLexIntake — notebook {report.notebook} · backend {report.backend}")
    for s in report.stages:
        mark = "ok " if s.ok else "ERR"
        print(f"  [{mark}] {s.name:<12} {s.detail}")
    print(
        f"\n  emails: {len(report.emails_markdown)}"
        f" · converted: {len(report.converted)}"
        f" · uploaded: {len(report.uploaded)}"
        f" · deduped: {len(report.deduped)}"
        f" · locked-deferred: {len(report.skipped_locked)}"
        f" · errors: {len(report.errors)}"
    )
    for e in report.errors:
        print(f"  ! {e}")


def cmd_init(args) -> int:
    """Initialize a new workspace for LexIntake.
    
    Creates the necessary directory structure and writes the initial config
    file so that the user can begin dropping emails and running the pipeline.
    """
    ws = Path(args.workspace).resolve()
    # Create the workspace directory if it doesn't exist
    ws.mkdir(parents=True, exist_ok=True)
    
    # Load or initialize the configuration
    cfg = LexConfig.load(ws)
    cfg.notebook = args.notebook
    if args.backend:
        cfg.backend = args.backend
    if args.provider:
        cfg.provider = args.provider
        
    # Save the configuration back to the workspace
    path = cfg.save()
    
    # Create the initial input directory for the user to drop files
    (ws / "01_mail_in").mkdir(exist_ok=True)
    print(f"initialized {path}")
    print(f"drop .eml/.msg/.mbox files into {ws / '01_mail_in'} then: lexintake run")
    return 0


def cmd_run(args) -> int:
    """Execute the core LexIntake pipeline (Stages 2-5).
    
    This command processes any emails in the input directory, converts
    attachments, uploads to NotebookLM, and generates review artifacts.
    """
    # Defer heavy imports until the command is actually run to keep CLI snappy
    from .pipeline import LexIntakePipeline

    cfg = _load(args)
    if not cfg.notebook:
        # Require a NotebookLM notebook ID to upload documents to
        print("no notebook configured; run `lexintake init` or pass --notebook",
              file=sys.stderr)
        return 2
        
    # Instantiate and run the pipeline
    report = LexIntakePipeline(cfg).run()
    _print_report(report)
    
    # Return a non-zero exit code if any errors occurred during the run
    return 1 if report.errors else 0


def cmd_export(args) -> int:
    cfg = _load(args)
    cap = get_capability(cfg.provider)
    if not cap.ready:
        print(f"provider {cfg.provider!r} not ready: {cap.explain()}", file=sys.stderr)
        return 2
    if not args.execute:
        print(
            "DRY RUN — add --execute to drive the browser.\n"
            f"  provider={cfg.provider} mailbox={cfg.mail_provider} "
            f"query={args.query!r} max={cfg.max_messages}"
        )
        return 0
    downloads = Path(args.workspace).resolve() / "01_mail_in"
    downloads.mkdir(parents=True, exist_ok=True)
    if cfg.provider == "gemini":
        from .providers.gemini import run_export_gemini

        run_export_gemini(
            mail_provider=cfg.mail_provider,
            query=args.query,
            download_dir=downloads,
            profile_dir=Path(args.workspace) / ".browser-profile",
            max_messages=cfg.max_messages,
        )
    else:
        # Instead of a stub, we now implement the full Playwright loop for OpenAI/Anthropic.
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print(
                f"{cfg.provider} export requires playwright. Run `pip install lexintake[browser]`",
                file=sys.stderr,
            )
            return 2
            
        from .providers.harness import BrowserExecutor
        
        # Determine the task prompt based on the user's query and config
        task_prompt = (
            f"Export the {cfg.max_messages} most recent messages matching the query "
            f"'{args.query}' as .eml downloads into the current downloads folder."
        )
        
        print(f"Launching {cfg.provider} computer-use agent. Please log in if prompted.")
        with sync_playwright() as p:
            # Launch an interactive browser so the user can log in if needed
            browser = p.chromium.launch(headless=False, downloads_path=str(downloads))
            # Create a new context holding the downloads path
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                accept_downloads=True
            )
            page = context.new_page()
            
            # Navigate to the appropriate mail provider
            mail_url = "https://outlook.office.com" if cfg.mail_provider == "outlook" else "https://mail.google.com"
            page.goto(mail_url)
            
            # Pause to let the user log in before handing control to the agent
            input("Log in if necessary, prepare the view, then press Enter to start the agent... ")
            
            executor = BrowserExecutor(page)
            if cfg.provider == "openai":
                from .providers.openai_cua import run_export_openai
                run_export_openai(task_prompt, executor)
            elif cfg.provider == "anthropic":
                from .providers.anthropic_cua import run_export_anthropic
                run_export_anthropic(task_prompt, executor)
                
            browser.close()
    
    # After export completes, continue with the regular run pipeline
    return cmd_run(args)


def cmd_status(args) -> int:
    from nlm.config import load_config
    from nlm.manifest import Manifest

    cfg = _load(args)
    state = Path(args.workspace).resolve() / ".nlm"
    if not state.is_dir():
        print("no runs yet — `lexintake run` first")
        return 0
    manifest = Manifest(load_config(str(state)).db_path)
    rows = manifest.list_sources(cfg.notebook or None)
    print(f"notebook {cfg.notebook}: {len(rows)} tracked source(s)")
    for r in rows:
        status = getattr(r.status, "value", r.status)
        print(f"  [{status:<9}] {r.orig_name:<40} {r.content_hash[:12]}")
    audits = sorted((Path(args.workspace) / "_audit").glob("run-*.json"))
    if audits:
        print(f"last run: {audits[-1].name}")
    return 0


def cmd_doctor(args) -> int:
    from . import winsafe

    ws = Path(args.workspace).resolve()
    print(f"lexintake {__version__} · python {sys.version.split()[0]}")
    print(f"workspace: {ws}  ({CONFIG_NAME} "
          f"{'found' if (ws / CONFIG_NAME).is_file() else 'missing — run init'})")
    if winsafe.is_cloud_synced(ws):
        print("  ! workspace is OneDrive/UNC-synced: fine, but pause sync during runs")
    print("providers:")
    for cap in available_providers():
        print(f"  {cap.provider:<10} {cap.explain()}")
    folders = winsafe.discover_mail_folders()
    if folders:
        print("detected mail/export folders:")
        for label, path in folders:
            print(f"  {label:<20} {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lexintake", description=__doc__)
    p.add_argument("--version", action="version", version=f"lexintake {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def ws(sp, *, notebook_required=False):
        sp.add_argument("workspace", nargs="?", default=".",
                        help="case workspace directory (default: current)")
        sp.add_argument("--notebook", required=notebook_required,
                        help="NotebookLM notebook id")
        sp.add_argument("--backend", choices=["stub", "enterprise"])
        sp.add_argument("--provider", choices=["gemini", "openai", "anthropic"])

    sp = sub.add_parser("init", help="create lexintake.toml + folders")
    ws(sp, notebook_required=True)
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("run", help="Stages 2-5: convert, dedupe, upload, artifacts")
    ws(sp)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("export", help="Stage 1 browser export, then run")
    ws(sp)
    sp.add_argument("--query", required=True, help="mailbox search query")
    sp.add_argument("--execute", action="store_true",
                    help="actually drive the browser (default: dry run)")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("status", help="tracked sources + last audit record")
    ws(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("doctor", help="environment / provider readiness check")
    ws(sp)
    sp.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
