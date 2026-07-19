"""Workflow harness — state management for HSPICE SRAM Vmin project.

Usage:
    python -m src.harness status              # Show current phase, queue, docs
    python -m src.harness phase <name>        # Transition to new phase
    python -m src.harness bg-add <task_id>    # Register background task
    python -m src.harness bg-done <task_id>   # Complete background task
    python -m src.harness bg-list             # List pending background tasks
    python -m src.harness check-session       # Run session start checklist
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_FILE = (HERE.parent.parent / "docs" / "workflow_state.json").resolve()

# Windows cp949 compatibility
if sys.stdout.encoding.lower() in ("cp949", "euc-kr"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

STATE_SCHEMA = {
    "required_keys": [
        "_format_version", "project", "phase", "phase_label",
        "phase_history", "bg_queue", "bg_queue_history",
        "documentation", "open_questions", "session_start_checklist",
    ]
}


def load_state() -> dict:
    if not STATE_FILE.exists():
        print(f"ERROR: State file not found: {STATE_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)

    for key in STATE_SCHEMA["required_keys"]:
        if key not in state:
            print(f"ERROR: Missing required key '{key}' in state file", file=sys.stderr)
            sys.exit(1)
    return state


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")


def cmd_status():
    state = load_state()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print(f"=== Workflow State @ {now} ===")
    print(f"Phase:     {state['phase']} ({state['phase_label']})")
    print(f"Project:   {state['project']}")
    print()

    print("--- Phase History ---")
    for entry in state["phase_history"]:
        icon = {"completed": "✅", "in_progress": "⏳", "failed": "❌"}.get(
            entry["status"], "❓"
        )
        print(f"  {icon} {entry['phase']}: {entry['summary']}")
    print()

    print("--- Background Task Queue ---")
    if state["bg_queue"]:
        for tid in state["bg_queue"]:
            print(f"  ⏳ {tid}")
    else:
        print("  (empty)")
    print()

    print("--- Documentation ---")
    docs = state["documentation"]
    print(f"  Trial log:      {docs.get('trial_log_updated', 'never')}")
    print(f"  Phase summary:  {docs.get('phase_summary_updated', 'never')}")
    print(f"  Decision files: {len(docs.get('decisions_logged', []))}")
    print()

    print("--- Session Start Checklist ---")
    cl = state.get("session_start_checklist", {})
    for k, v in cl.items():
        icon = "✅" if v else "⬜"
        label = k.replace("_", " ").title()
        print(f"  {icon} {label}: {v}")
    print()

    print("--- Open Questions ---")
    for q in state.get("open_questions", []):
        print(f"  ❓ {q}")

    return 0


def cmd_phase(new_phase: str | None):
    if not new_phase:
        print("ERROR: Usage: harness phase <name>", file=sys.stderr)
        return 1

    state = load_state()

    old_phase = state["phase"]
    state["phase_history"].append({
        "phase": old_phase,
        "status": "completed",
        "summary": f"Transition to {new_phase}",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })

    state["phase"] = new_phase
    state["phase_label"] = new_phase
    state["documentation"]["phase_summary_updated"] = None  # flag as needs update
    save_state(state)

    print(f"Phase transition: {old_phase} → {new_phase}")
    print(f"IMPORTANT: Write phase summary .md in docs/decisions/")
    return 0


def cmd_bg_add(task_id: str | None):
    if not task_id:
        print("ERROR: Usage: harness bg-add <task_id>", file=sys.stderr)
        return 1

    state = load_state()
    state["bg_queue"].append(task_id)
    state["bg_queue_history"].append({
        "task_id": task_id,
        "action": "add",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    save_state(state)
    print(f"Registered: {task_id}")
    return 0


def cmd_bg_done(task_id: str | None):
    if not task_id:
        print("ERROR: Usage: harness bg-done <task_id>", file=sys.stderr)
        return 1

    state = load_state()
    if task_id in state["bg_queue"]:
        state["bg_queue"].remove(task_id)
        state["bg_queue_history"].append({
            "task_id": task_id,
            "action": "done",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        save_state(state)
        print(f"Completed: {task_id}")
    else:
        print(f"WARNING: {task_id} not found in queue", file=sys.stderr)
        return 1
    return 0


def cmd_bg_list():
    state = load_state()
    if state["bg_queue"]:
        print("Pending background tasks:")
        for tid in state["bg_queue"]:
            print(f"  ⏳ {tid}")
    else:
        print("No pending background tasks.")
    return 0


def cmd_check_session():
    """Run session start checklist and mark items done."""
    state = load_state()
    cl = state["session_start_checklist"]

    checks = {
        "read_harness": "docs/harness.md",
        "read_workflow_state": "docs/workflow_state.json",
        "read_agents_md": "AGENTS.md",
        "read_decisions": "docs/decisions/*.md",
        "check_bg_queue": "bg_queue empty?",
    }

    all_done = True
    for key, file in checks.items():
        if cl.get(key):
            print(f"  ✅ {file}")
        else:
            print(f"  ⬜ {file} — NOT DONE")
            all_done = False

    if all_done:
        print("\n✅ Session init complete. Proceed with Phase 3 work.")
    else:
        print(f"\n⚠️  {sum(1 for k in checks if not cl.get(k))} item(s) pending.")

    return 0 if all_done else 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0

    cmd = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else None

    commands = {
        "status": cmd_status,
        "phase": lambda: cmd_phase(arg),
        "bg-add": lambda: cmd_bg_add(arg),
        "bg-done": lambda: cmd_bg_done(arg),
        "bg-list": cmd_bg_list,
        "check-session": cmd_check_session,
    }

    handler = commands.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(f"Available: {', '.join(commands.keys())}", file=sys.stderr)
        return 1

    return handler()


if __name__ == "__main__":
    sys.exit(main())
