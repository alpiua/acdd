# ACDD execution optimization review

This note is the current optimization backlog for the ACDD task runner,
architecture contract, adapters, and skills. The score is priority/impact from
`1` (low value or high risk) to `10` (high value with a clear safe benefit).
Quality gates, four-partition coverage, frozen-input checks, and fail-closed
behavior are not optimization targets to remove.

| Score | Area | Current state | Safe optimization | Status |
|---:|---|---|---|---|
| 10 | command transport | Legacy external callers may still pass a shell command string to the runner. | Owner wrappers should pass typed argv vectors; retain `--check-command` only for legacy callers and migrate them to repeated `--check-arg`. Keep shell only as an explicitly declared launcher capability. | wrapper fixed; legacy migration remains |
| 9 | output memory | Launcher stdout/stderr is captured in full before JSON parsing; malformed responses retain only a bounded redacted excerpt in task evidence. | Stream bounded JSONL/usage records, retain only the terminal candidate and bounded redacted excerpts, and keep full transcripts outside the repository. | next hardening |
| 9 | prompt maintenance | Inspector/coordinator prompts are large inline JSON builders in `run_architecture.py`. | Move static prompt contracts into adapter-relative templates or typed builders and test their hashes/required fields. This lowers drift and prompt tokens without weakening validation. | next hardening |
| 9 | host binding | Generic ACDD validates host-neutral command launchers. | Keep host binding and model routing in owner adapters; add typed executor capabilities only when another transport requires them. | implemented |
| 8 | finding identity | Coordinator source references use positional `partition:index` refs. | Use the inspector finding `id` as the primary stable ref and retain positional refs only as a legacy alias. This prevents reconciliation drift when finding order changes. | next hardening |
| 8 | snapshot model | The runner computes the candidate digest before launch and recomputes it for the terminal frozen-input recheck. | Return a typed snapshot manifest from fingerprinting and compare the same declared path/hash set at the end; do not create a new candidate or broaden the file set. | next hardening |
| 8 | usage transport | The runner normalizes common JSON usage shapes, including Pi `message_end`, but must infer the shape. | Let each launcher optionally declare a usage extractor/schema while retaining the generic normalizers as fallback. Missing usage remains provenance `available: false`, not a fabricated zero-cost claim. | next hardening |
| 7 | coordinator payload | Coordinator receives validated partitions, discovery receipts, and source findings, which can be larger than the semantic decision needs. | Send bounded partition summaries plus typed findings/evidence and the frozen semantic authority; retain full validated partition objects for local validation and receipts. | measure first |
| 7 | retry scheduling | Each failed inspector retries within its own future while other inspectors continue. | Keep this behavior; add per-partition timeout and cancellation only after the full wave has been allowed to terminate. Never abort the wave early. | preserve, add timeout |
| 6 | validation duplication | `check` validates the task and the runner validates adapter/contract/result again. | Share an immutable preflight result object between wrapper and runner only when both execute in the same process. Preserve the second boundary for standalone runner invocation. | optional |
| 6 | static contract lint | YAML schema, owner contract, adapter launcher rules, and prompt contracts are validated in separate code paths. | Add a single contract-lint command that reports cross-file mismatches before launch. Do not make runtime validation dependent on documentation generation. | next tooling |
| 5 | logging | Human-readable stderr logs are useful but not a machine-readable execution ledger. | Add an optional JSON event log outside the repository with session, partition, phase, duration, and outcome; keep default stderr concise. | optional |
| 4 | model routing | Owner adapters may route different models to inspectors and the coordinator. | Measure quality and cost before changing models. Do not move routing into generic ACDD fields or infer it from `runtime`. | preserve |
| 3 | derived refreshes | Adapter-owned derived-state refreshes can be expensive. | Keep one refresh after candidate freeze and one final handoff refresh; never refresh after each individual edit. | implemented policy |
| 2 | executor capacity | Some executors cannot run all four inspectors simultaneously. | Preserve four partitions; use the executor's maximum safe concurrency and start the coordinator only after all four validate. Use another executor only when true four-way wall-time is required. | adapter tradeoff |

## Non-negotiable acceptance checks

Every optimization must continue to prove:

- exactly four inspectors share one candidate fingerprint;
- the coordinator starts only after all four validated outputs terminate;
- typed candidate defects distinguish task-design failures from unfinished code;
- changed task/code inputs produce `BLOCKED` and no receipt;
- runtime/schema/transport `BLOCKED` does not consume the material FAIL cap;
- PASS writes one evidence object and one receipt;
- all bounded findings and normalized usage survive terminal recording;
- task architecture launchers are split and unambiguous; other gate modes use
  their declared single-launcher form.
