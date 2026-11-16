---
id: "forge.skill.kirion-session-host"
source_repo: "Kirch-Nairu/Operation-FORGE.kirion"
source_ref: "eabbfbabdbb22d8684fb2c3d80767b8547852b83"
source_path: ".agents/skills/kirion-session-host/SKILL.md"
source_status: "CANDIDATE"
source_blob_sha: "0c37a217ecd88b8b94e02b9dce683611b34ac528"
tags: [forge, arsenal, candidate]
---

# Kirion Session Host

**CANDIDATE / OPT_IN_ONLY.** Full canonical skill text at pinned PR #7 SHA. Reading this is not authority or automatic host installation.

[Exact SKILL.md](https://github.com/Kirch-Nairu/Operation-FORGE.kirion/blob/eabbfbabdbb22d8684fb2c3d80767b8547852b83/.agents/skills/kirion-session-host/SKILL.md) · [[00 Skill Index]] · [[Specialist Selection]] · [[00 HOME]]

## Canonical contract

# ChatGPT + GitHub first; host-independent authority
1. Read explicit mission and verify connected GitHub login matches the assigned worker. Nairu/Kirch-Nairu, Jane/Kirion-Jane, Nox/Kirion-Nox, and Lucien/Kirion-Lucien are distinct identities; the active assignment decides role and permissions.
2. Fetch target AGENTS.md, current feature contract/issue/PR, remote branch HEAD, and skill SKILL.md through the authenticated GitHub connector at a verified source ref.
3. Use the current chat's available VM/container for disposable clones, source inspection, tests and artifacts; do not assume another chat shares its filesystem, credentials, internet access or running processes. If VM cannot reach private GitHub, use the connector for authenticated remote work and VM for safe local checks.
4. Source-write only when authorized, with one writer per owned path; review separately under the authenticated nonauthor identity. Verify all remote tool results rather than claiming success from intent.
5. Persist material evidence to the authorized GitHub issue/PR/branch; temporary paths are not cross-session handoffs. Return a short capsule: role, repo, feature, issue/PR, exact SHA, changed paths, tests run/not run, blockers and next permitted action.
Codex/Antigravity may discover these same SKILL.md files in .agents/skills; user-wide installs differ by host. No VM availability, role, skill, GitHub permission, merge, deployment or approval is inferred.
