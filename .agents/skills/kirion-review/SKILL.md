---
name: kirion-review
description: Independently inspect frozen exact-SHA code and integrated user journeys for material bugs, false confidence, unauthorized scope and protected invariants.
---

# Independent nonauthor review
Verify GitHub identity and candidate SHA, base, approved contract and changes. Distinguish reported checks from independently observed ones. Review full risk-bearing consumer path, security/business negative cases, compatibility and runtime evidence. Do not approve beyond inspected scope.
Findings require severity, source path/line or artifact, violated invariant, reproducible failure mechanism and minimum correction. Preserve previous findings that remain valid after bounded rework; target only changed dependency surfaces.
Publish a formal verdict under actual project policy. Review is not merge or deployment authorization. Do not edit the source being independently judged.
