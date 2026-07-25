# ACDD Versioning

Keep a contract at `v1` while existing documents and adapters remain valid
without changing their meaning.

## Compatible changes

The following may ship in place:

- optional fields with a deterministic default;
- new validation for a state that was already invalid;
- new scripts, examples, documentation, or diagnostics;
- accepting an additional owner-selected runtime while preserving gate
  semantics.

## Breaking changes

Create a new version when a change:

- adds, removes, or reorders a required gate;
- removes a capability, status, or required adapter role;
- changes the meaning of existing evidence or fingerprints;
- makes a previously valid receipt or adapter structurally invalid;
- changes required receipt fields or routing ownership.

## Migration

1. Add the new profile or contract beside the old version.
2. Keep old readers available while active documents use the old version.
3. Make new documents write the new version.
4. Provide a dry-run validator or mechanical migration when document edits are
   required.
5. Record profile-only task migrations with
   `acdd/contract-change/v1 kind: profile-migration`.
6. Preserve completed receipts with their recorded `contractRevision`; never
   backfill evidence that the old verifier did not produce.
7. Remove the old version only after no active document or adapter references
   it.

Semantic task changes are not profile migrations. Record them as
`kind: semantic-change`, provide authorization, and invalidate affected gates.
