# Planning set contract

The primary plan records the planning execution contract, manifest, evidence and contradiction register, architecture coherence, shape decisions, decomposition, receipts, blockers, and handoff.

The structural hierarchy is `roadmap → phases → milestones → tasks`. A plan is not a hierarchy level. Bind each plan to exactly one roadmap, phase, milestone, or task owner and declare every phase it spans; a plan may span multiple phases without changing ownership.

Every changed artifact must be declared before mutation and remain under the supplied adapter's authority. Roadmap and phase changes require ordered dependencies, membership, backlinks, and no premature execution claims. Milestones belong to phases and own task membership, production paths, gates, and evidence-bound closure. Task drafts belong to milestones and require owners, prerequisites, expected evidence, and resolved implementation decisions. Host-specific activation metadata and execution queues remain adapter concerns.
