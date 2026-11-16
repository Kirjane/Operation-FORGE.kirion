---
id: "forge.skill.kirion-runtime"
source_repo: "Kirch-Nairu/Operation-FORGE.kirion"
source_ref: "eabbfbabdbb22d8684fb2c3d80767b8547852b83"
source_path: ".agents/skills/kirion-runtime/SKILL.md"
source_status: "CANDIDATE"
source_blob_sha: "a45ed5cfaaac8711b7d3a9aee5cc97b861434a5d"
tags: [forge, arsenal, candidate]
---

# Kirion Runtime

**CANDIDATE / OPT_IN_ONLY.** Full canonical skill text at pinned PR #7 SHA. Reading this is not authority or automatic host installation.

[Exact SKILL.md](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/blob/eabbfbabdbb22d8684fb2c3d80767b8547852b83/.agents/skills/kirion-runtime/SKILL.md) · [[00 Skill Index]] · [[Specialist Selection]] · [[00 HOME]]

## Canonical contract

# Operational runtime
Inventory target environment, database and storage paths, authentication/network, installer service user, licenses, backups and rollback before any mutation.
Offline first means durable local writes and restart recovery; do not invent cloud dependencies. On Windows separate Program Files binaries from writable ProgramData; verify non-elevated reopen and preserved machine license. On Linux isolate services, backup/recovery, remote access, networking and logs. Use disposable data for migrations and destructive probes.
Report BUILD, INSTALLED, RUNTIME_OBSERVED, DEPLOYED and OPERATIONAL as different evidence states. Never reset client data/license or expose service ports without explicit authority.
