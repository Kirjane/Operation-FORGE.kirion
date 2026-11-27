"""Canonical command proposals. A route is never an authorization or invocation.

The host must independently authenticate the actor and observe mission state before
using a route, then apply the existing mission contract and journal preflight.
Natural language discovery remains a Maintainer interaction, not an executable command.
"""
from dataclasses import dataclass
from types import MappingProxyType

from .authority import ALLOWED_TRANSITIONS, CANONICAL_STATES, VALID_FORMAL_ROLES, validate_lifecycle_transition


@dataclass(frozen=True)
class Command:
    aliases: tuple[str, ...]
    roles: frozenset[str]
    stages: frozenset[str]
    effect: str
    next_stage: str | None
    entrypoint: str


ROLES = frozenset(VALID_FORMAL_ROLES) | {"Engineer", "Acceptance Agent"}
STAGES = frozenset(CANONICAL_STATES)
COMMANDS = MappingProxyType({
    "forge": Command(("/forge",), frozenset({"Maintainer", "Engineer"}), STAGES,
                     "READ", None, "BOOTSTRAP_CHATGPT.md"),
    "help": Command(("/help.forge", "/forge.help"), ROLES, STAGES,
                    "READ", None, "command_registry"),
    "resume": Command(("/resume",), ROLES, STAGES,
                      "READ", None, "protocols/recovery.md"),
    "status": Command(("/forge.status",), ROLES, STAGES,
                      "READ", None, "factory:status"),
    "plan": Command(("/forge.plan",), frozenset({"Maintainer"}), frozenset({"PLANNED"}),
                    "READ", None, "protocols/reconnaissance.md"),
    "assign": Command(("/forge.assign",), frozenset({"Maintainer"}), frozenset({"PLANNED"}),
                      "LOCAL_ARTIFACT", None, "factory:supervised-handoff"),
    "write": Command(("/forge.write",), frozenset({"Code Writer", "Integration Writer"}), frozenset({"AUTHORIZED"}),
                     "SOURCE_WRITE", "ACTIVE", "protocols/writer-execution.md"),
    "review": Command(("/forge.review",), frozenset({"Reviewer"}), frozenset({"READY"}),
                      "READ", None, "factory:inspect-candidate"),
    "repair": Command(("/forge.repair",), frozenset({"Code Writer", "Integration Writer"}), frozenset({"REWORK"}),
                      "SOURCE_WRITE", "ACTIVE", "self_healing_repair"),
    "verify": Command(("/forge.verify",), ROLES, frozenset({"READY", "UNDER_REVIEW"}),
                      "PROCESS_TEST", None, "factory:test"),
    "accept": Command(("/forge.accept",), frozenset({"Engineer", "Acceptance Agent"}), frozenset({"UNDER_REVIEW"}),
                      "LOCAL_ARTIFACT", "ACCEPTED", "roles/acceptance.md"),
    "deliver": Command(("/forge.deliver",), frozenset({"Maintainer"}), frozenset({"ACCEPTED", "INTEGRATED"}),
                       "REMOTE_EFFECT", None, "protocols/promotion.md"),
})


def _aliases(commands):
    aliases = {}
    for name, item in commands.items():
        if item.next_stage is not None and any(item.next_stage not in ALLOWED_TRANSITIONS[stage] for stage in item.stages):
            raise ValueError("ILLEGAL_CANONICAL_TRANSITION")
        if item.next_stage is not None:
            if item.effect in {"READ", "NETWORK_READ"}:
                raise ValueError("READ_COMMAND_CANNOT_PROPOSE_MUTATION")
            for role in item.roles:
                for stage in item.stages:
                    validate_lifecycle_transition(stage, item.next_stage, actor_role=role, is_author=False)
        for alias in item.aliases:
            if alias in aliases:
                raise ValueError("DUPLICATE_COMMAND_ALIAS")
            aliases[alias] = name
    return MappingProxyType(aliases)


ALIASES = _aliases(COMMANDS)


def describe_commands():
    return [{"command": name, "aliases": list(item.aliases), "roles": sorted(item.roles),
             "stages": sorted(item.stages), "effect": item.effect, "entrypoint": item.entrypoint}
            for name, item in COMMANDS.items()]


def propose_command(alias, *, observed_role, observed_stage):
    """Pure routing. Caller-provided observations are NOT authenticated by this function."""
    result = {"authority_granted": False, "invoked": False, "promotion_authorized": False}
    if type(alias) is not str or alias not in ALIASES:
        return dict(result, status="BLOCKED", reason="UNKNOWN_COMMAND")
    if type(observed_role) is not str or observed_role not in ROLES:
        return dict(result, status="BLOCKED", reason="UNKNOWN_ROLE")
    if type(observed_stage) is not str or observed_stage not in STAGES:
        return dict(result, status="BLOCKED", reason="UNKNOWN_STAGE")
    name = ALIASES[alias]
    item = COMMANDS[name]
    if observed_role not in item.roles:
        return dict(result, status="BLOCKED", reason="ROLE_NOT_ELIGIBLE")
    if observed_stage not in item.stages:
        return dict(result, status="BLOCKED", reason="STAGE_NOT_ELIGIBLE")
    return dict(result, status="PROPOSED", command=name, role=observed_role,
                expected_stage=observed_stage, next_stage=item.next_stage or observed_stage,
                effect=item.effect, entrypoint=item.entrypoint,
                requires_trusted_preflight=True)
