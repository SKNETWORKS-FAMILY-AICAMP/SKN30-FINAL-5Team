DECISION_ENDPOINT_CODE = "POST_DECISIONS"
# v6 omits profile attention areas: they are Check-in UI prefill, while only
# user-confirmed Daily Check-in pains/discomforts are decision inputs. The column is a
# plain string, so rows written at prior versions keep their value and stay replayable.
DECISION_INPUT_SCHEMA_VERSION = "decision-input-v6"
DECISION_RESPONSE_SCHEMA_VERSION = "decision-response-v2"
DECISION_POLICY_VERSION = "decision-policy-v3"
DECISION_GRAPH_VERSION = "decision-graph-v2"
DECISION_EXPLANATION_TEMPLATE_VERSION = "decision-explanation-template-v1"
DECISION_EXPLANATION_PROMPT_VERSION = "decision-explanation-prompt-v1"
V3_DECISION_EXPLANATION_TEMPLATE_VERSION = "v3-decision-explanation-template-v1"
V3_DECISION_EXPLANATION_PROMPT_VERSION = "v3-decision-explanation-prompt-v1"
