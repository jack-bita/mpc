"""control — owns Flags, AuditEvents, EditEvents (the edit history, written by its own trigger), Attachments,
ImportJobs and Notifications [R2].

Layer 0, beside core (ADR-0035): every app writes here, so its code imports only core.
"""
