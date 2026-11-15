---
name: kirion-session-host
description: Execute Kirion worker tasks in ChatGPT conversations using the connected GitHub app and current session VM when available; support Codex and Antigravity without fabricated identity or cross-chat state.
---

# ChatGPT + GitHub first; host-independent authority
1. Read explicit mission and verify connected GitHub login matches the assigned worker. Nairu/Kirch-Nairu, Jane/Kirion-Jane, Nox/Kirion-Nox, and Lucien/Kirion-Lucien are distinct identities; the active assignment decides role and permissions.
2. Fetch target AGENTS.md, current feature contract/issue/PR, remote branch HEAD, and skill SKILL.md through the authenticated GitHub connector at a verified source ref.
3. Use the current chat's available VM/container for disposable clones, source inspection, tests and artifacts; do not assume another chat shares its filesystem, credentials, internet access or running processes. If VM cannot reach private GitHub, use the connector for authenticated remote work and VM for safe local checks.
4. Source-write only when authorized, with one writer per owned path; review separately under the authenticated nonauthor identity. Verify all remote tool results rather than claiming success from intent.
5. Persist material evidence to the authorized GitHub issue/PR/branch; temporary paths are not cross-session handoffs. Return a short capsule: role, repo, feature, issue/PR, exact SHA, changed paths, tests run/not run, blockers and next permitted action.
Codex/Antigravity may discover these same SKILL.md files in .agents/skills; user-wide installs differ by host. No VM availability, role, skill, GitHub permission, merge, deployment or approval is inferred.
