"""Canonical command proposals. A route is never an authorization or invocation.

The host must independently authenticate the actor and observe mission state before
using a route, then apply the existing mission contract and journal preflight.
Natural language discovery remains a Maintainer interaction, not an executable command.
"""
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class Command:
    aliases: tuple[str, ...]
    roles: frozenset[str]
    stages: frozenset[str]
    effect: str
    next_stage: str | None
    entrypoint: str


ROLES = frozenset({"MAINTAINER", "WRITER", "REVIEWER", "ENGINEER"})
STAGES = frozenset({"DISCOVERY", "PLANNED", "ASSIGNED", "CANDIDATE", "REVIEWED", "ACCEPTED"})
COMMANDS = MappingProxyType({
    "forge": Command(("/forge",), frozenset({"MAINTAINER", "ENGINEER"}), STAGES,
                     "READ", None, "BOOTSTRAP_CHATGPT.md"),
    "help": Command(("/help.forge", "/forge.help"), ROLES, STAGES,
                    "READ", None, "command_registry"),
    "resume": Command(("/resume",), ROLES, STAGES,
                      "READ", None, "protocols/recovery.md"),
    "status": Command(("/forge.status",), ROLES, STAGES,
                      "READ", None, "factory:status"),
    "plan": Command(("/forge.plan",), frozenset({"MAINTAINER"}), frozenset({"DISCOVERY", "PLANNED"}),
                    "READ", "PLANNED", "protocols/reconnaissance.md"),
    "assign": Command(("/forge.assign",), frozenset({"MAINTAINER"}), frozenset({"PLANNED"}),
                      "SOURCE_WRITE", "ASSIGNED", "factory:supervised-handoff"),
    "write": Command(("/forge.write",), frozenset({"WRITER"}), frozenset({"ASSIGNED"}),
                     "SOURCE_WRITE", "CANDIDATE", "protocols/writer-execution.md"),
    "review": Command(("/forge.review",), frozenset({"REVIEWER"}), frozenset({"CANDIDATE"}),
                      "READ", "REVIEWED", "factory:inspect-candidate"),
    "repair": Command(("/forge.repair",), frozenset({"WRITER"}), frozenset({"CANDIDATE", "REVIEWED"}),
                      "SOURCE_WRITE", "CANDIDATE", "self_healing_repair"),
    "verify": Command(("/forge.verify",), ROLES, frozenset({"CANDIDATE", "REVIEWED"}),
                      "PROCESS_TEST", None, "factory:test"),
    "accept": Command(("/forge.accept",), frozenset({"ENGINEER", "MAINTAINER"}), frozenset({"REVIEWED"}),
                      "SOURCE_WRITE", "ACCEPTED", "roles/acceptance.md"),
    "deliver": Command(("/forge.deliver",), frozenset({"MAINTAINER"}), frozenset({"REVIEWED", "ACCEPTED"}),
                       "REMOTE_EFFECT", None, "protocols/promotion.md"),
})


def _aliases(commands):
    aliases = {}
    for name, item in commands.items():
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
