---
name: kirion-runtime
description: Handle offline/local-first desktop and server hosting, installations, data/backup/restore, licensing and recovery with realistic observed evidence.
---

# Operational runtime
Inventory target environment, database and storage paths, authentication/network, installer service user, licenses, backups and rollback before any mutation.
Offline first means durable local writes and restart recovery; do not invent cloud dependencies. On Windows separate Program Files binaries from writable ProgramData; verify non-elevated reopen and preserved machine license. On Linux isolate services, backup/recovery, remote access, networking and logs. Use disposable data for migrations and destructive probes.
Report BUILD, INSTALLED, RUNTIME_OBSERVED, DEPLOYED and OPERATIONAL as different evidence states. Never reset client data/license or expose service ports without explicit authority.
