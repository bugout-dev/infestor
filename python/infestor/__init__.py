# Try to set up reporting. If it doesn't work because imported dependencies are not present in
# the user's environment, fail quietly.
try:
    from .report import infestor_reporter, infestor_tags

    infestor_reporter.system_report(tags=infestor_tags)
    infestor_reporter.setup_excepthook(tags=infestor_tags)
except Exception:
    pass

# TODO (yhtiyar):
# In PackageFileManager make checking call by call_type not by hard coding
# Add Decorator adder transformer,
# Add DecoratorRemoverTransformer, integrate it to PackageFileManager
# Improve RemoveCallsTransformer : it is now removing by source
# Add unittests for : listing calls/decorators, RemoveCallTransformer,
# tests with remove relative import testcase

