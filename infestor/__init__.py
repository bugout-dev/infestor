# Try to set up reporting. If it doesn't work because imported dependencies are not present in
# the user's environment, fail quietly.
try:
    from .report import infestor_reporter, infestor_tags

    infestor_reporter.system_report(tags=infestor_tags)
    infestor_reporter.setup_excepthook(tags=infestor_tags)
except Exception:
    pass
