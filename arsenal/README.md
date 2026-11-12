# KIRION Multi-Host Skill Arsenal v0.2 — DRAFT
**Primary execution:** Kirion workers in separate ChatGPT conversations, using their authenticated GitHub connector and that conversation's available VM. **Other hosts:** Codex and Antigravity, both sharing the same portable `.agents/skills/<name>/SKILL.md` contracts.

This is an isolated **candidate**, not a third Forge governance system or an adopted change to One Talibon, Salryn, other projects, PR #4 or PR #6. Project AGENTS.md, current Engineer decisions, exact Git/runtime and approved contracts outrank generic skills.

## Start a ChatGPT worker conversation
Read [WORKER_START.md](adapters/chatgpt/WORKER_START.md) and paste its short mission header into the Jane, Nox, Lucien or Nairu conversation. The conversation must use **its own** connected GitHub identity to fetch the current target AGENTS.md, issue/PR and current commit; then read `.agents/skills/kirion-core/SKILL.md`, `kirion-dispatch` and `kirion-session-host` at an exact observed arsenal ref. Load 1–3 task-relevant specialists. The VM is disposable and not automatically shared between chats; persist meaningful evidence to GitHub.

## Skill areas
Cognition, quality worker, architecture, debugging, financial/business logic, security, QA, frontend, code review, integration, offline/runtime, evidence, session host and skill smith. One-off task skills are temporary; never promote without review and approval.

## Other hosts
- Codex: repo `.agents/skills`, user-wide `~/.agents/skills`.
- Antigravity: repo `.agents/skills`, user-wide `~/.gemini/config/skills`.
- ChatGPT: no guaranteed automatic local-skill discovery across worker chats; use the connected GitHub app and the bootstrap pointer, or explicitly configured ChatGPT Project instructions.

## What skills don't prove
Loading a skill does not prove an agent complied. CI, review and source inspection don't prove installed runtime or production behavior. No synthetic test alone proves fewer hallucinations or a performance increase. GitHub identity, exact SHA, acceptance and final release must be independently established for the actual mission.

## Delivery state
16 skills staged in this draft branch, not on main. No auto merge, deployment, client policy migration, production changes, or model/VM privileges are granted.
