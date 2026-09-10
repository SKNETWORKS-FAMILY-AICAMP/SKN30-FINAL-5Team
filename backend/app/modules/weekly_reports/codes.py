WEEKLY_REPORT_ENDPOINT_CODE = "POST_WEEKLY_REPORT"
WEEKLY_REPORT_ACK_ENDPOINT_CODE = "POST_WEEKLY_REPORT_ACKNOWLEDGEMENT"
# v2 renamed the safety-stop count. v3 added reproducible performed-workout
# aggregates. v4 adds deterministic feedback, condition, recorded-reason, and
# actual-recommendation evidence for the six-section report. Existing reports
# keep their older snapshots.
WEEKLY_REPORT_INPUT_SCHEMA_VERSION = "weekly-report-input-v4"
WEEKLY_REPORT_POLICY_VERSION = "weekly-report-policy-v3"
WEEKLY_REPORT_RESPONSE_SCHEMA_VERSION = "weekly-report-response-v2"

__all__ = [
    "WEEKLY_REPORT_ACK_ENDPOINT_CODE",
    "WEEKLY_REPORT_ENDPOINT_CODE",
    "WEEKLY_REPORT_INPUT_SCHEMA_VERSION",
    "WEEKLY_REPORT_POLICY_VERSION",
    "WEEKLY_REPORT_RESPONSE_SCHEMA_VERSION",
]
