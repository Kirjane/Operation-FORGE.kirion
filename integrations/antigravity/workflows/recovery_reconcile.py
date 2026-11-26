# Native Antigravity workflow entry; host authority is never inferred from args.
try:
    from integrations.antigravity.factory.native_boundary import native_workflow_entry
except ImportError:
    print({"status": "BLOCKED", "reason": "NATIVE_BOUNDARY_IMPORT_UNAVAILABLE", "invoked": False})
else:
    print(native_workflow_entry("recovery_reconcile", "antigravity", args))
