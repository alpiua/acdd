# Plan receipt lifecycle

Use the same inline receipt model as `acdd/task/v1`.

1. Declare typed workspace-relative source, test, configuration, generated,
   dependency, environment, and accepted-finding paths under `## ACDD inputs`.
2. Keep bounded `acdd/gate-evidence/v1` objects under
   `## ACDD gate evidence`.
3. Reference evidence only as `evidence=<id>` from the primary plan receipt
   table.
4. Let strict validation build the canonical snapshot in memory from the bound
   plan, selected profile, receipt contract, supplied adapters, and declared
   paths.
5. Persist no generated provenance files or reviewer transcript.

Missing, duplicate, escaping, undeclared, stale, or adapter-unauthorized inputs
fail closed. Basis gates use their configured validity inputs; live review,
publish, and handoff use every declared input type.

Use `rationale` evidence only for an allowed `inapplicable` receipt. Publish and
handoff cannot pass with blockers or a stale/nonterminal predecessor.
