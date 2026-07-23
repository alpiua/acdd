# Architecture gate

Load only for `architecture/v1`.

An architecture receipt may pass only when the proposed slice identifies:

1. the canonical owner and desired end state;
2. the production trigger → caller → contract → owner → consumer path;
3. contract, identity/authority, lifecycle, failure, rollback, and cleanup seams;
4. direct and alternate writers/readers, migration/compatibility paths, and their removal owner;
5. one named negative or cross-boundary proof for every changed invariant;
6. every unresolved contradiction as a blocker.

Classify the solution:

- **canonical** — implements the desired owner and removes invalid states;
- **migration-compatible** — temporarily bridges to the canonical owner, with a linked removal condition and a failure it must not hide;
- **blocked** — the canonical owner or safe migration cannot yet be determined.

A schema, helper, compatibility alias, test-only caller, or reviewer-authored prose is not a production path. The reviewer must be independent of the task author and must return PASS or FAIL with exact evidence.
