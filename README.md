# AOS (Autonomous Engineering System)

AOS is a controlled, self-hosted, FOSS-only autonomous software-engineering machine. Given an objective, it researches, plans, implements, tests, debugs, reviews, and hardens code in a durable loop until verified evidence supports completion — or a human decision is required.

## Phase 0: Contracts & Threat Model

Phase 0 establishes the foundational contracts and security boundaries:
- **Contracts (`aos.contracts`)**: Typed, immutable Pydantic v2 schemas for `Task`, `Run`, `Artifact`, `Event`, `Approval`, `Policy`, and `Worker`.
- **State Machines (`aos.contracts.transitions`)**: Pure functional transitions producing explicit state updates and typed event payloads for `TaskStatus` and `RunStatus`.
- **Threat Model (`aos.docs.threat_model.md`)**: Containment architecture modeling the coding agent as the contained actor across 10 security actions.
- **Reference Policy (`aos.docs.sample_policy.json`)**: Declarative policy rules covering Master Specification §8.

## Usage & Development

Install dependencies into a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .[dev]
```

Run contract tests:

```powershell
.\.venv\Scripts\python -m pytest aos/tests/ -v
```

Generate JSON schema:

```powershell
.\.venv\Scripts\python -c "from aos.contracts.task import Task; import json; print(json.dumps(Task.model_json_schema(), indent=2))"
```

