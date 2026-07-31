---
name: acdd-v2-build
description: Run the build/v1 ACDD gate.
---

# build/v1

## Load

Read the integrated workspace, profile, and implementation adapter. Load only
`runtime-and-integration`, then append its `promptAppend` fragment if present.

## runtime-and-integration

Run the owner-bound command on the integrated tree. It must prove the intended
runtime behavior and integration/repository-quality contract together. A timeout
or non-zero result is not a pass.

Tune the binding, not the run: `timeoutSeconds` (default 300) sets the proof
budget for this repository, and `promptAppend` adds repository context. Both
are declared in the implementation adapter and hashed into the gate
fingerprint, so changing them re-opens the gate.

## Evidence

Record the command artifact and finalize only when its fingerprint is current.
Use gate-level `inapplicable` only with a declared profile reason and real
evidence.
