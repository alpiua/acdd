# Receipt lifecycle

Each required gate has exactly one current task-owned receipt with:

- gate ID and a `pending`, `blocked`, or gate-allowed terminal status from
  `contracts/receipt/v1.yaml`;
- bounded evidence or artifact references;
- the SHA-256 fingerprint of a referenced `acdd/input-set/v1` manifest;
- UTC recording time;
- explicit blockers or an empty-blocker statement.

The manifest contains sorted identities and digests for task, source, tests,
configuration, generated inputs, dependencies, environment, and accepted review
findings. Do not hand-author opaque component digests. Declare exact files and
typed Git heads in an `acdd/input-spec/v1` file, then build both the canonical
manifest and its auditable component lock:

```bash
python3 scripts/build_input_set.py <input-spec.json> \
  --root <workspace-root> \
  --output <input-manifest.json> \
  --details <input-components.json>
python3 scripts/fingerprint_inputs.py <input-manifest.json>
```

The two commands must print the same fingerprint. `build_input_set.py` rejects
missing files, path escapes, duplicate components, missing invalidation kinds and
missing/duplicate transformed Markdown headings. Only exact task receipt sections
may use `excludeMarkdownSections`. A section such as `Execution gates` may use
`normalizeMarkdownCheckboxesInSections` so completion marks are receipt state while
gate wording remains an invalidation input. Task objective, contract, matrices,
gate text, owners and blocker semantics always remain fingerprint inputs.

The task adapter defines the concrete item IDs and references both generated
artifacts in evidence. Receipt-only evidence writes do not alter the task input;
all other task-contract changes invalidate affected receipts.

A blocked receipt requires current evidence, fingerprint, and timestamp. A changed
input returns affected receipts to `pending`; all later gate receipts must also be
nonterminal. Never copy an old result into a new fingerprint.
`architecture/v1` and `review/v1` identify the independent review adapter result.
`red/v1` uses `expected_failure`; `inapplicable` requires a task-owned rationale.
`handoff/v1` cannot pass before every prior gate is terminal and blockers are
empty.
