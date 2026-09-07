WEEKLY_REPORT_ENDPOINT_CODE = "POST_WEEKLY_REPORT"
WEEKLY_REPORT_ACK_ENDPOINT_CODE = "POST_WEEKLY_REPORT_ACKNOWLEDGEMENT"
# v2 renamed the safety-stop count. v3 adds reproducible performed-workout
# aggregates (progress, calorie estimate, completed-block training shape, and
# prior-report comparison). Existing reports keep their older snapshots.
WEEKLY_REPORT_INPUT_SCHEMA_VERSION = "weekly-report-input-v3"
WEEKLY_REPORT_POLICY_VERSION = "weekly-report-policy-v2"
WEEKLY_REPORT_RESPONSE_SCHEMA_VERSION = "weekly-report-response-v1"

__all__ = [
    "WEEKLY_REPORT_ACK_ENDPOINT_CODE",
    "WEEKLY_REPORT_ENDPOINT_CODE",
    "WEEKLY_REPORT_INPUT_SCHEMA_VERSION",
    "WEEKLY_REPORT_POLICY_VERSION",
    "WEEKLY_REPORT_RESPONSE_SCHEMA_VERSION",
]
