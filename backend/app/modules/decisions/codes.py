DECISION_ENDPOINT_CODE = "POST_DECISIONS"
# v5 adds the latest difficulty feedback to the snapshot (ADR-0018 D2). The column is a
# plain string, so rows written at v4 keep their value and stay replayable.
DECISION_INPUT_SCHEMA_VERSION = "decision-input-v5"
DECISION_RESPONSE_SCHEMA_VERSION = "decision-response-v2"
DECISION_POLICY_VERSION = "decision-policy-v3"
DECISION_GRAPH_VERSION = "decision-graph-v2"
DECISION_EXPLANATION_TEMPLATE_VERSION = "decision-explanation-template-v1"
DECISION_EXPLANATION_PROMPT_VERSION = "decision-explanation-prompt-v1"
V3_DECISION_EXPLANATION_TEMPLATE_VERSION = "v3-decision-explanation-template-v1"
V3_DECISION_EXPLANATION_PROMPT_VERSION = "v3-decision-explanation-prompt-v1"
