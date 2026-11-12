# KIRION — ChatGPT worker conversation launch
Use this as a **short copied mission header** and fill the blanks using real assignment data:

```text
KIRION FORGE — ACTIVATE [NAIRU / JANE / NOX / LUCIEN]
Role / mission: [read-only reviewer OR bounded writer OR Maintainer]
Target repo: [owner/repo]
GitHub identity expected: [Kirch-Nairu / Kirion-Jane / Kirion-Nox / Kirion-Lucien]
Issue / PR / contract: [actual links]
Starting SHA: [full SHA, or DISCOVER_CURRENT]
Owned paths: [authorized allowlist]
Skill source: Kirch-Nairu/Operation-FORGE.kirion, proposal/kirion-skill-arsenal-multihost-v0-2
Do not adopt this proposed skill set as new project policy.
Use the connected GitHub app first. Verify its login. Read target AGENTS.md,
contract/issue, current remote SHA; then fetch .agents/skills skill
source at verified ref (repository root path is .agents/skills/<name>/SKILL.md).
Load kirion-core, kirion-dispatch, kirion-session-host and only relevant specialists.
Use this chat's available VM for safe disposable source/tests. No assumption
that other chats share its files, Git credentials or runtime.
Work only within authorized scope. Report real tests/NOT_RUN and exact SHA.
Persist evidence in authorized GitHub issue/PR; return concise resume pointer.
No self-review, imaginary worker identity, merge, deploy, policy adoption
or production mutation without explicit project/human authorization.
```

The **GitHub identity must be observed**, not assumed from the prompt. A ChatGPT session does not automatically gain the other workers' credentials. If no GitHub connector/VM is available, report the limitation and use only permitted narrower actions.

The user may configure the compact Project instruction in `arsenal/adapters/chatgpt/PROJECT_INSTRUCTIONS.fragment.md`; this repo proposal does **not** edit the user's ChatGPT Project or global settings. After a chat reset, recheck remote HEAD and fetch affected state delta rather than replaying old conversations.
