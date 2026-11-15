# KIRION Forge

**Remember durably. Build aggressively. Promote deliberately.**

> Agents are ephemeral. Authority is explicit. Evidence is durable. Memory belongs to the project.

KIRION Forge is a **maintainer-governed engineering operating model** for AI-assisted software delivery. It combines explicit authority, bounded writing assignments, source-backed context, recoverable execution, independent review and deliberate Git promotion. The integrated repository also carries **Project Second Brain**, the cognition/context layer, and the **Kirion Skill Arsenal**, a portable set of sixteen task-oriented Agent Skills.

This repository is an engineering control system and reference implementation—not a commercial hosted service, an automatically privileged agent, or proof that an AI-generated candidate is production-ready.

## Choose your starting point

| I want to... | Start with | What it does |
| --- | --- | --- |
| Start a project or act as Maintainer | [00_START_HERE](00_START_HERE/README.md) | Launch the existing Forge role and authority handshake |
| Execute an already-authorized coding task | [Code Writer launcher](00_START_HERE/CODE_WRITER_BOOTSTRAP_HANDOFF.md) | Reconstruct the approved scope and source before writing |
| Integrate authorized branches | [Integration Writer launcher](00_START_HERE/INTEGRATION_WRITER_BOOTSTRAP_HANDOFF.md) | Reconcile ancestry, ownership, conflicts and acceptance boundaries |
| Bootstrap Forge in a new ChatGPT conversation | [ChatGPT-first bootstrap](arsenal/CHATGPT_BOOTSTRAP.md) | Verify GitHub identity, detect project state and load minimum applicable skills |
| Choose greenfield versus active/maintenance/recovery routing | [Project-state guide](arsenal/PROJECT_STATES.md) | Route by project origin and current work mode without re-nesting an existing project |
| Use portable specialist skills in ChatGPT, Codex or Antigravity | [Skill Arsenal handbook](arsenal/README.md) | Find the correct skills, pin source, configure a host and use evidence |
| Launch a connected ChatGPT worker | [ChatGPT Worker Start](arsenal/adapters/chatgpt/WORKER_START.md) | Create a bounded mission with authenticated GitHub identity |
| Evaluate adoption or a release | [Adoption and promotion runbook](arsenal/ADOPTION.md) | Keep skill availability, worker defaults, merge and release separate |
| See concrete mission examples | [Arsenal examples](arsenal/EXAMPLES.md) | Copy patterns for UI, financial, review, runtime and continuation tasks |
| Understand the two-system boundary | [System Boundary](SYSTEM_BOUNDARY.md) | Learn which system controls context versus repository mutation |

**Existing Forge users:** the Skill Arsenal is additive. The accepted role, handoff, evidence and promotion protocols remain authoritative. Merely loading a skill does not replace them.

## Repository status and claim boundaries

- **Forge maturity:** declared **NEST-2 — Governed (Genesis)** in [the NEST record](.forge/NEST.md). Do not equate documentation or green CI with NEST-3, NEST-4, or stable platform maturity.
- **Accepted authority:** read **remote main HEAD** and [Forge authority](.forge/AUTHORITY.md). A SHA mentioned in this README, in a chat, or in a historical report is not proof of current authority.
- **Skill distribution:** source files live under [.agents/skills](.agents/skills) in the proposal and become available on main only after an authorized promotion. Consult [the arsenal manifest](arsenal/manifest.json) and the actual Git ref for the adoption state.
- **Human decisions:** the project Engineer controls scope, integration and adoption; client/product acceptance remains with the relevant project owner. A maintainer report or reviewer finding is not itself permission to deploy.
- **Experimental evidence:** source-backed field exercises and bounded comparisons exist; they do **not** establish a quantified causal reduction in hallucinations, defects, time or cost.

Do not infer that a private repository, ChatGPT account, local VM, secret, Codex or Antigravity installation is shared across sessions.

## Architecture at a glance

~~~text
User / Engineer-approved outcome
             |
     Project / Forge authority
             |
  Second Brain (optional context)
       routing, rigor, knowledge
             |
         bounded handoff
             |
      Kirion Skill Arsenal
   core + dispatch + specialists
             |
        one source writer
             |
      candidate commit / PR
             |
     independent verification
             |
   Maintainer acceptance decision
             |
 authorized non-force promotion
             |
    verified authority + memory
~~~

The **read path** (classification, routing, context compilation) and **write path** (authorization, implementation, review, acceptance, promotion) must not be conflated. The normative division is [SYSTEM_BOUNDARY.md](SYSTEM_BOUNDARY.md); evidence translations are in [EVIDENCE_CROSSWALK.md](EVIDENCE_CROSSWALK.md).

## Five-minute first run

1. Identify the **target repository, desired user-visible outcome, active issue/PR, assigned role and authorized work**.
2. Open [00_START_HERE](00_START_HERE/README.md). For a connected ChatGPT worker using portable skills, also open [WORKER_START.md](arsenal/adapters/chatgpt/WORKER_START.md).
3. Resolve the **current immutable 40-character Forge skill-source SHA** in GitHub. Pin that commit; do not pass a mutable branch name as immutable mission authority.
4. Read the target project's approved AGENTS/feature contract, observe the remote source state, and verify the active GitHub account identity. A persona name in a prompt is not authentication.
5. Load **kirion-core**, **kirion-dispatch**, and **kirion-session-host** for ChatGPT GitHub-connected workers. Then load only **one to three applicable work specialists**, unless distinct risks justify more.
6. Work inside the existing assigned scope. Test positive, negative and edge paths in the **actual relevant environment**; report unavailable checks as NOT_RUN.
7. Persist evidence to the authorized GitHub issue/PR. Never auto-promote the writer's work or claim a test run, review, installation, device check or deployment without evidence.

For a simple read-only task, omit unnecessary specialist layers and do not create a new task skill or project approval gate.

## The sixteen portable skills

Every skill is a plain-text SKILL.md under the matching directory in [.agents/skills](.agents/skills). They are not executables, credentials or server-enforced rules.

| Skill | Intended use |
| --- | --- |
| kirion-core | Universal evidence, authority, risk and scope rules |
| kirion-dispatch | Load only relevant specialist guidance |
| kirion-session-host | ChatGPT GitHub identity, VM isolation and handoffs |
| kirion-cognition | Reconcile stale history, current Git and conflicting claims |
| kirion-worker | Bounded source implementation with meaningful regression proof |
| kirion-architecture | Existing/approved interfaces, vertical path and minimal design |
| kirion-debug | Root cause, discriminating reproduction and narrow repairs |
| kirion-business-logic | Financial, inventory, procurement and workflow invariants |
| kirion-security | Authorization, trust boundaries, secrets and replay |
| kirion-qa | Risk-scaled browser, API, DB, host and document validation |
| kirion-frontend | Responsive and accessible client-authoritative UI |
| kirion-review | Independent, nonauthor, exact-SHA findings and verdict |
| kirion-integrator | Branch lineage, collisions, consumer and integration proof |
| kirion-runtime | Offline desktop, installations, licensing and recovery |
| kirion-evidence | Accurate provenance, TESTED versus REPORTED or NOT_RUN |
| kirion-skill-smith | Rare opt-in disposable mission-specific skill generation |

Full selection guidance, safety boundaries and scenarios are in the [Skill Arsenal handbook](arsenal/README.md).

## Supported host surfaces

| Host | Expected skill discovery / loading | Important limitation |
| --- | --- | --- |
| ChatGPT + connected GitHub | Worker explicitly fetches pinned SKILL.md files; optional [Project instructions](arsenal/adapters/chatgpt/PROJECT_INSTRUCTIONS.fragment.md) | No implied automatic installation or cross-conversation filesystem |
| Codex | Repository-local .agents/skills, optional user skills depending on host configuration | Repo policy and actual Codex capabilities still control mutations |
| Antigravity | Repository-local .agents/skills, optional local user skill configuration | No implicit access to ChatGPT credentials or other workers' sessions |

These are **documented adapter contracts**, not a guarantee that a particular external host/version automatically discovers every skill. Inspect the host's actual behavior. Never copy private secrets into a skill file.

## Roles, authority and execution

Forge distinguishes **Maintainer**, **Code Writer**, **Integration Writer**, **Reviewer** and **Acceptance Agent**. The identity used for a GitHub comment or commit must be the authenticated account, not the persona requested in the chat. A source author cannot become an independent reviewer simply by changing account connectors inside the same authoring conversation.

Before any substantial write, check:

- Repository and remote; exact source SHA and branch.
- Engineer-approved user outcome and current project contract.
- Which actor owns the affected files and the active feature.
- Cross-branch consumers, dependencies and review limitations.
- Relevant risk/negative cases and actual test environment.
- Which operations are forbidden, including secrets, client data, force pushes and production changes.
- What evidence and independent acceptance the **target project** actually requires.

Source output is a **candidate**. CI is **verification evidence**; review is an **opinion on inspected scope**; acceptance is an **authority decision**; deployment and live operation are separate observed states.

## Validation from the repository root

Requires a local checkout with Python 3. The commands below are real repository entrypoints, but are **not claims that they ran in your current environment**.

~~~bash
python tools/forge_check.py repo
python tools/forge_check.py schemas
python tools/forge_check.py links
python tools/forge_check.py nest
python -m unittest discover -s arsenal/tests -v
python tools/entity_check.py
~~~

The **Forge Validate** workflow executes the structural/schema/link/NEST checks and automatically discovers arsenal unit tests. The integrated entity validation also checks Forge/Second Brain contracts. Passing these checks does not establish browser, device, installed-host, application data, financial ledger or production acceptance.

The new arsenal checks verify **manifest count, skill names and required metadata, entrypoints, and existing host-adapter skill references**, plus adversarial generator behavior. See [tests](arsenal/tests) and [the CI workflow](.github/workflows/forge-validate.yml).

## Repository map

| Location | Responsibility |
| --- | --- |
| [.forge](.forge) | Forge's own current authority, architecture, NEST and engineering memory |
| [AGENTS.md](AGENTS.md) | Constitution and core behavioral boundaries |
| [BOOTSTRAP.md](BOOTSTRAP.md) | Universal role/capability handshake |
| [00_START_HERE](00_START_HERE/README.md) | Short human launchers |
| [.agents/skills](.agents/skills) | Sixteen portable specialist contracts |
| [arsenal](arsenal/README.md) | Host adapters, generator, tests and operations |
| [roles](roles/maintainer.md) | Maintainer and worker role contracts |
| [protocols](protocols/promotion.md) | State transitions and promotion protocols |
| [doctrine](doctrine/decision-surface-compression.md) | Foundational reasoning and decision-surface compression |
| [memory](memory/README.md) | Source-backed recovery and continuity |
| [git](git/README.md) | Branch and promotion safety |
| [testing](testing/README.md) | Verification and evidence rules |
| [security](security/README.md) | Instruction trust, secrets and destructive-action boundaries |
| [second-brain](second-brain/README.md) | Integrated cognition, routing and context compilation |
| [tools](tools/README.md) | Structural and governance checks |

## Safety and operational limits

- No skill may grant GitHub permissions, customer-data access, a role change, deployment rights or client signoff.
- An unauthorized/unknown branch, stale SHA, conflicting reviewer identity or unverified project policy is a reason to **stop the affected mutation**, not invent a workaround.
- **Real systems:** enforce permissions on the real server; test financial and retained-data invariants against safe test databases.
- **Explicit static demonstrations:** clearly labeled fictional data and simulated roles are acceptable when the approved contract authorizes them. They are not live logins, production authorization, valid issued documents or genuine cash workflows.
- Source inspection cannot prove a runtime observation. A green workflow cannot prove a deployment or a physical device test.
- Avoid replaying huge historical chat transcripts. Rehydrate from current repository memory, the active issue and exact Git state.
- The repository may be private. Access and connected accounts are individually authorized; no passwords, OTPs, signing keys, credentials or sensitive client records belong in the Skill Arsenal.

## How a version becomes an accepted standard

Read [ADOPTION.md](arsenal/ADOPTION.md). The acceptance sequence is:

**candidate SHA → meaningful CI → separate nonauthor review → explicit Engineer acceptance and target-ref authorization → authority precheck → non-force promotion → remote verification → durable memory update**.

Merging the skill sources into Forge main **does not** automatically update a ChatGPT Project, modify customer projects, install user-wide skills or approve client releases. Those are separate user/Engineer actions.

## Documentation and contribution expectations

Use the [Skill Arsenal handbook](arsenal/README.md), [adoption runbook](arsenal/ADOPTION.md) and [mission examples](arsenal/EXAMPLES.md) rather than duplicating policies or introducing a new control plane.

Contributions should be scoped to a real defect/approved improvement, tested at the exact source SHA, and independently reviewed under Forge policy. Do not rewrite history to hide a failed pilot, run another experiment without authorization or claim improvement beyond supported evidence.
