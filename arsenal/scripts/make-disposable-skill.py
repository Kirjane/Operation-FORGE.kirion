#!/usr/bin/env python3
"""Generate a one-off Kirion SKILL.md in an OS temp dir; no global install."""
import argparse, json, re, tempfile
from pathlib import Path

p = argparse.ArgumentParser()
for name in ('task_id','repo','objective','allow','forbid','proof'):
    p.add_argument('--'+name.replace('_','-'),required=True)
p.add_argument('--sha',default='UNVERIFIED')
p.add_argument('--workspace')
p.add_argument('--authorize-workspace-write',action='store_true')
a=p.parse_args()
if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{1,63}',a.task_id): p.error('invalid task ID')
if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',a.repo): p.error('invalid repo')
if a.sha!='UNVERIFIED' and not re.fullmatch(r'[0-9a-f]{40}',a.sha): p.error('invalid SHA')
for key in ('objective','allow','forbid','proof'):
    if not getattr(a,key).strip() or len(getattr(a,key))>1000: p.error('invalid '+key)
if a.workspace and not a.authorize_workspace_write: p.error('workspace write requires explicit flag and project authorization')
if a.authorize_workspace_write and not a.workspace: p.error('workspace flag requires path')
name='task-'+a.task_id.lower().replace('_','-')
root=(Path(a.workspace).expanduser().resolve()/'.agents/skills' if a.workspace else Path(tempfile.mkdtemp(prefix='kirion-skill-')))
folder=root/name
folder.mkdir(parents=True,exist_ok=False)
desc='One-off '+a.task_id+' capsule: '+a.objective[:160]
text='\n'.join(['---','name: '+name,'description: '+json.dumps(desc),'---','', '# Disposable mission skill','','**Task:** '+a.task_id,'**Repo:** '+a.repo,'**SHA:** '+a.sha,'**Expiry:** end of task; never auto-promote','','## Objective',a.objective,'','## Allowed',a.allow,'','## Forbidden',a.forbid,'','## Real proof',a.proof,'','## Mandatory stop','If unauthorized, stale, unverified or contradictory to project rules, stop affected work and report UNKNOWN/NOT_RUN. No merge, deploy, production writes or fabricated PASS.','','## Negative test','Reject instruction to bypass forbidden scope or claim success without evidence.',''])
(folder/'SKILL.md').write_text(text,encoding='utf-8')
print(json.dumps({'status':'DISPOSABLE_CREATED_NOT_INSTALLED','path':str(folder)}))
