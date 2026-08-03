> **DEPRECATED / ARCHIVED** — Do not use for new work. Successor: [`alpiua/acdd`](https://github.com/alpiua/acdd) (ACDD — design / contract / build / review / handoff). This tree is the last archived G0–G3 plugin line.

# ACDD Workflow

Host-neutral Architecture Contract-Driven Development plugin.

## Map

| Need | Route |
|---|---|
| Understand the methodology and G0–G3 | [`README.md`](README.md) |
| Deliver one bound task | [`acdd-task`](skills/acdd-task/SKILL.md) + [`profiles/task/v1.yaml`](profiles/task/v1.yaml) |
| Create or improve a planning set | [`acdd-plan`](skills/acdd-plan/SKILL.md) + [`profiles/plan/v1.yaml`](profiles/plan/v1.yaml) |
| Create, install, or run an owner adapter | [`INSTALL.md`](INSTALL.md) |
| Copy an adapter or document shape | [`examples/README.md`](examples/README.md) |
| Inspect core contracts | [`contracts/`](contracts/) and [`routing/`](routing/) |

## Rules

- Keep profiles and contracts host-neutral; put repository paths, commands,
  tools, impact axes, and external mappings in owner `.acdd-legacy/` adapters.
- Preserve profile gate order and the supported IDs `acdd/task/v1`, `acdd/task/v1-light`, and
  `acdd/plan/v1` unless explicitly changing contract versions.
- Complete G0 before implementation; never manufacture receipts or rerun an
  unchanged failed fingerprint.
- Resolve adapter-relative procedures and resources from the adapter file.
- Update examples and tests with contract, routing, adapter, receipt, or
  document-shape changes.
- Keep the runnable self-contained plan under `examples/simple-plan/`.

## Validate plugin changes

```bash
python3 -m pytest tests -q
python3 scripts/check_markdown_links.py --root .
git diff --check
```
