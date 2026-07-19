# AGENTS.md — Project documentation

Architecture decision records, phase plans, and workflow state.

---

## Structure

```
docs/
├── decisions/      # 15 ADR files (CRITICAL — read first)
├── plans/          # 7 active phase plans
├── harness.md      # Workflow state documentation
└── workflow_state.json  # Phase state (managed by src/harness.py)
```

---

## Decisions (docs/decisions/)

Architecture Decision Records (ADRs) documenting key tradeoffs:
- Format: `.md` files with options considered and rationale
- **Read first** when modifying architecture
- Current count: 15 files

---

## Plans (docs/plans/)

Active phase plans tracking project progress:
- Primary: `phase2_to_paper_plan.md` (Phase 2-5 roadmap)
- 12-figure list, Go/No-Go criteria per stage
- Current count: 7 files

---

## Workflow state

`workflow_state.json` tracks:
- Current phase and phase history
- Background task queue
- Documentation status
- Open questions
- Session start checklist

Managed by `python/src/harness.py` CLI:
```bash
cd python && python -m src.harness status
cd python && python -m src.harness phase <name>
cd python && python -m src.harness bg-add <id>
cd python && python -m src.harness bg-done <id>
cd python && python -m src.harness check-session
```

---

## Anti-patterns

- **Do NOT modify** `workflow_state.json` directly — use `harness.py` CLI
- **Do NOT delete** decision records without documenting reason
- **Do NOT commit** session-specific state changes without team review
