from .version import INFESTOR_VERSION

from humbug.consent import HumbugConsent, environment_variable_opt_in, yes
from humbug.report import HumbugReporter

INFESTOR_REPORTING_TOKEN = "6ec64442-40e3-41ff-afe3-d818c023cd41"

infestor_consent = HumbugConsent(
    environment_variable_opt_in("INFESTOR_REPORTING_ENABLED", yes)
)

infestor_reporter = HumbugReporter(
    name=f"infestor",
    consent=infestor_consent,
    bugout_token=INFESTOR_REPORTING_TOKEN,
)

infestor_tags = [f"version:{INFESTOR_VERSION}"]
