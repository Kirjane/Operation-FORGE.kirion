# Supervised ChatGPT engineering

The native workflow bridge is unavailable. The safe usable route is a
human-supervised separate conversation using existing GitHub connectors and
the actual target project's approved issue authority. No automatic chat
creation, account switching, tool interception or live dispatch is implied.

## Start and resume

1. Maintainer creates or verifies a bounded issue directive and exact target
   repository ID/name, branch and HEAD; freezes the authorized Forge registry
   SHA, v2 mission JSON and stage context. Do not use a moving branch as a pin.
2. Use the authorized worker's separate ChatGPT conversation and [WORKER_START](WORKER_START.md).
   Verify the connector's actual login/numeric ID, directive author,
   exact current remote head and permitted role/scope before any connector write.
   Publish one START on the authorized issue. If scope or actor cannot be
   verified, return a read-only proposal; do not use another account.
3. Fetch registry metadata at the exact approved SHA, then each selected source
   at its per-entry pinned commit/path/blob. Verify byte counts and SHA-256 when
   tools support it. Record retrieval distinctly from actual consumption.
   Frontend tasks require the canonical declaration/profile and explicit
   domains (including mandatory entrypoint/evidence). No missing required
   reference may be silently omitted.
4. For a separately authorized connector write, inspect the exact parent tree,
   propose a bounded changed-path set, reject excluded/protected files and
   unexpected semantic changes, apply only allowed source changes on the
   assigned branch and read back the exact tree/parent/head. Require an
   expected-head ref update where available; if unavailable or moved, stop.
   These are manual/operator-controlled connector actions, not a native
   enforcement or CAS guarantee by this package. Frontend writes requiring
   trusted native actor grants remain blocked by the harness; source-only
   proposals remain available. Do not merge, deploy or mutate main.
5. Record actual evidence, test commands/results or NOT_RUN, exact final SHA,
   and one CLOSE. A different authorized nonauthor reviewer opens a separate
   session and checks the frozen candidate. No self-review or acceptance.

## Local source-only helper

From a clone with the exact authorized Git objects available, use:

~~~sh
python -m integrations.antigravity.factory.cli supervised-handoff --packet mission.json --context-config context.json --source-root . --workflow feature_delivery
python -m integrations.antigravity.factory.cli inspect-candidate --packet mission.json --target-root /path/to/disposable-or-readonly-target --candidate-sha <exact-candidate-sha>
~~~

The first command validates the contract and exports verified retrieved text
and existing stage documents as JSON; it does not start a worker. Keep its
output in an authorized private context. The second reports exact local Git
candidate ancestry/tree/changed paths and raw diff digest; it does not apply
a patch or establish remote state. Both helpers have no credential provider,
native grant, delivery transport or independent acceptance. A frontend
candidate can be inspected even if path policy remains unauthorized.

Context JSON is operator-reported, keyed internally by exact contract digest.
Supply actual run_id, revision, profile, host="chatgpt", stage, task,
max_context_bytes, actor_id, host_id, context_id, attempt_ordinal, and
required_extra including "kirion-session-host". Set include_routes and
optional_extra consistently with the packet's ordered skill file projection.
For frontend add explicit frontend_domains and optional_frontend_domains,
with max_reference_files and a byte allowance sufficient for the mandatory
documents. Add the approved source authority and READ scope covering the
actual declaration, profile and reference paths to the packet. For inherited
cognition provide the existing verified brain_stage_context and brain_run_id.
No configuration value creates authority or proves native consumption.

## Stage semantics

Native entries return BLOCKED plus the inert stages from
factory/workflow_stages.py: discovery/decomposition then architecture and
security; implementation then independent exact-SHA review; repair
classification then bounded root-cause fix and independent recheck;
adversarial review; integration collision audit; and read-only recovery.
Each stage requires its own existing authorization. Requirements, drift and
resource stops are not automatically repaired. UNKNOWN never authorizes
replay. No stage automatically activates another persona.
