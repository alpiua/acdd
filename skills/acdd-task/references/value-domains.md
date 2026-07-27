# Persisted contract propagation

Add this optional task section whenever persisted acceptance or meaning can change. This includes value sets, ranges, nullability, formats, length or precision limits, required fields, defaults, discriminators, shapes, and relational invariants.

```yaml
## Persisted contract propagation
apiVersion: acdd/persisted-contracts/v2
kind: persisted-contracts
domains:
  - id: measurement.accepted-range
    field: measurements.value
    contractKind: numeric-range
    change: changed
    compatibilityImpact: restriction
    beforeContract: {minimum: 0, maximum: 100}
    afterContract: {minimum: 10, maximum: 90}
    discovery:
      roots: [contextunity]
      terms: [measurement_range, validate_measurement, measurements_value_check]
      files:
- {path: services/api/measurement_input.py, roles: [producer, public-type]}
- {path: services/worker/measurement_writer.py, roles: [writer]}
- {path: packages/storage/measurement_schema.sql, roles: [schema, migration]}
- {path: services/api/measurement_reader.py, roles: [reader]}
- {path: services/api/tests/test_measurement_range.py, roles: [proof]}
    compatibility:
      strategy: preflight-reject
compatibilityPaths: [services/api/measurement_reader.py]
      proofIds: [proof.measurement-range]
    proofIds: [proof.measurement-range]
```

Use `change: unchanged|new|changed|removed`. Classify compatibility separately as `none`, `compatible-expansion`, `restriction`, `reinterpretation`, or `removal`. Any restriction, reinterpretation, or removal forbids `not-required`; it requires a backfill, compatibility bridge, or fail-closed preflight, owned compatibility paths, and executable proofs.

The validator scans each declared root, prunes dependency, cache, generated-build, and VCS directories, and applies exact terms. It is bounded to 20,000 inspected text files and 256 matching files per contract. Exceeding a bound fails with an instruction to narrow roots or use more precise identifiers; it does not demand an unbounded disposition list. Every resulting file must be classified with a pipeline role or `unrelated` plus rationale. All non-unrelated files must be task inputs. Required roles are producer, writer, schema, reader, public-type, and proof.

Choose terms that identify the contract rather than generic words such as `value`, `status`, or `visibility`. Discovery closure proves the declared exact searches were reconciled; architecture review and dependency traversal still prove repository-wide relationship closure.
