WEEKLY_REPORT_ENDPOINT_CODE = "POST_WEEKLY_REPORT"
WEEKLY_REPORT_ACK_ENDPOINT_CODE = "POST_WEEKLY_REPORT_ACKNOWLEDGEMENT"
# v2 renames the safety-stop count. The number itself is unchanged, but its meaning
# is: P1-C split the official completion state from the execution state, so a safety
# stop is no longer one of the completion outcomes. Reports generated at v1 keep
# their snapshot and their number; the version is what tells the two apart.
WEEKLY_REPORT_INPUT_SCHEMA_VERSION = "weekly-report-input-v2"
WEEKLY_REPORT_POLICY_VERSION = "weekly-report-policy-v1"
WEEKLY_REPORT_RESPONSE_SCHEMA_VERSION = "weekly-report-response-v1"

__all__ = [
    "WEEKLY_REPORT_ACK_ENDPOINT_CODE",
    "WEEKLY_REPORT_ENDPOINT_CODE",
    "WEEKLY_REPORT_INPUT_SCHEMA_VERSION",
    "WEEKLY_REPORT_POLICY_VERSION",
    "WEEKLY_REPORT_RESPONSE_SCHEMA_VERSION",
]
