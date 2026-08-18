"""Deterministic safety classification and approved-rule evaluation."""

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from enum import IntEnum, StrEnum

SAFETY_ENGINE_VERSION = "1.1.0"


class BodyAreaCode(StrEnum):
    NECK = "NECK"
    SHOULDER = "SHOULDER"
    ELBOW = "ELBOW"
    WRIST_HAND = "WRIST_HAND"
    UPPER_BACK = "UPPER_BACK"
    LOWER_BACK = "LOWER_BACK"
    HIP = "HIP"
    KNEE = "KNEE"
    ANKLE_FOOT = "ANKLE_FOOT"
    CHEST = "CHEST"
    ABDOMEN = "ABDOMEN"
    GENERALIZED = "GENERALIZED"
    OTHER = "OTHER"


class DiscomfortSeverityCode(IntEnum):
    NONE = 0
    MILD = 1
    MODERATE = 2
    SEVERE = 3


class AdverseReactionCode(StrEnum):
    CHEST_DISCOMFORT = "CHEST_DISCOMFORT"
    UNEXPECTED_SEVERE_SHORTNESS_OF_BREATH = "UNEXPECTED_SEVERE_SHORTNESS_OF_BREATH"
    SEVERE_DIZZINESS = "SEVERE_DIZZINESS"
    FAINTING = "FAINTING"
    SUDDEN_WEAKNESS_OR_NUMBNESS = "SUDDEN_WEAKNESS_OR_NUMBNESS"
    RAPID_OR_IRREGULAR_HEARTBEAT_WITH_SYMPTOMS = "RAPID_OR_IRREGULAR_HEARTBEAT_WITH_SYMPTOMS"
    SUDDEN_SEVERE_PAIN = "SUDDEN_SEVERE_PAIN"
    ACUTE_SWELLING_OR_DEFORMITY = "ACUTE_SWELLING_OR_DEFORMITY"
    CANNOT_BEAR_WEIGHT = "CANNOT_BEAR_WEIGHT"
    OTHER_SERIOUS_REACTION = "OTHER_SERIOUS_REACTION"


EMERGENCY_REACTION_CODES = frozenset(
    {
        AdverseReactionCode.CHEST_DISCOMFORT,
        AdverseReactionCode.UNEXPECTED_SEVERE_SHORTNESS_OF_BREATH,
        AdverseReactionCode.SEVERE_DIZZINESS,
        AdverseReactionCode.FAINTING,
        AdverseReactionCode.SUDDEN_WEAKNESS_OR_NUMBNESS,
        AdverseReactionCode.RAPID_OR_IRREGULAR_HEARTBEAT_WITH_SYMPTOMS,
        AdverseReactionCode.OTHER_SERIOUS_REACTION,
    }
)
ACUTE_MUSCULOSKELETAL_REACTION_CODES = frozenset(
    {
        AdverseReactionCode.SUDDEN_SEVERE_PAIN,
        AdverseReactionCode.ACUTE_SWELLING_OR_DEFORMITY,
        AdverseReactionCode.CANNOT_BEAR_WEIGHT,
    }
)


class SafetyStatusCode(StrEnum):
    PASS = "PASS"
    NEEDS_INPUT = "NEEDS_INPUT"
    REVISE = "REVISE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class SafetyRequiredActionCode(StrEnum):
    REST = "REST"
    STOP_AND_SEEK_HELP = "STOP_AND_SEEK_HELP"


class SafetyRuleScopeCode(StrEnum):
    EXERCISE = "EXERCISE"
    MOVEMENT_PATTERN = "MOVEMENT_PATTERN"


class SafetyRuleEffectCode(StrEnum):
    EXCLUDE = "EXCLUDE"
    CAUTION = "CAUTION"


class SafetyReviewStatusCode(StrEnum):
    DRAFT = "DRAFT"
    TECH_REVIEWED = "TECH_REVIEWED"
    DOMAIN_APPROVED = "DOMAIN_APPROVED"
    REJECTED = "REJECTED"
    DEPRECATED = "DEPRECATED"


class SafetyRuleAvailabilityCode(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    NOT_DOMAIN_APPROVED = "NOT_DOMAIN_APPROVED"
    NOT_PRODUCTION_ELIGIBLE = "NOT_PRODUCTION_ELIGIBLE"


class SafetyRuleError(ValueError):
    """Base exception for invalid safety-domain input."""


class InvalidSafetyInputError(SafetyRuleError):
    """Raised when safety input violates a documented structural invariant."""


def _require_non_empty(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidSafetyInputError(f"{field_name} must be a non-empty string")


def _require_unique(values: tuple[object, ...], *, field_name: str) -> None:
    if len(values) != len(set(values)):
        raise InvalidSafetyInputError(f"{field_name} must not contain duplicates")


@dataclass(frozen=True, slots=True)
class Discomfort:
    body_area_code: BodyAreaCode
    severity_code: DiscomfortSeverityCode

    def __post_init__(self) -> None:
        if not isinstance(self.body_area_code, BodyAreaCode):
            raise InvalidSafetyInputError("body_area_code must be an approved BodyAreaCode")
        if not isinstance(self.severity_code, DiscomfortSeverityCode):
            raise InvalidSafetyInputError(
                "severity_code must be an approved DiscomfortSeverityCode"
            )
        if self.severity_code is DiscomfortSeverityCode.NONE:
            raise InvalidSafetyInputError("NONE discomforts must be omitted from input")


@dataclass(frozen=True, slots=True)
class SafetyContext:
    discomforts: tuple[Discomfort, ...] = ()
    adverse_reaction_codes: tuple[AdverseReactionCode, ...] = ()
    attention_area_codes: tuple[BodyAreaCode, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.discomforts, tuple):
            raise InvalidSafetyInputError("discomforts must be an immutable tuple")
        if not isinstance(self.adverse_reaction_codes, tuple):
            raise InvalidSafetyInputError("adverse_reaction_codes must be an immutable tuple")
        if not isinstance(self.attention_area_codes, tuple):
            raise InvalidSafetyInputError("attention_area_codes must be an immutable tuple")
        if any(not isinstance(value, Discomfort) for value in self.discomforts):
            raise InvalidSafetyInputError("discomforts must contain only Discomfort values")
        if any(not isinstance(value, AdverseReactionCode) for value in self.adverse_reaction_codes):
            raise InvalidSafetyInputError(
                "adverse_reaction_codes must contain only AdverseReactionCode values"
            )
        if any(not isinstance(value, BodyAreaCode) for value in self.attention_area_codes):
            raise InvalidSafetyInputError(
                "attention_area_codes must contain only BodyAreaCode values"
            )
        _require_unique(
            tuple(discomfort.body_area_code for discomfort in self.discomforts),
            field_name="discomfort body areas",
        )
        _require_unique(self.adverse_reaction_codes, field_name="adverse_reaction_codes")
        _require_unique(self.attention_area_codes, field_name="attention_area_codes")


@dataclass(frozen=True, slots=True)
class SafetyCandidateItem:
    exercise_code: str
    catalog_version_code: str
    movement_pattern_code: str

    def __post_init__(self) -> None:
        _require_non_empty(self.exercise_code, field_name="exercise_code")
        _require_non_empty(self.catalog_version_code, field_name="catalog_version_code")
        _require_non_empty(self.movement_pattern_code, field_name="movement_pattern_code")


@dataclass(frozen=True, slots=True)
class SafetyCandidate:
    items: tuple[SafetyCandidateItem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or not self.items:
            raise InvalidSafetyInputError("candidate items must be a non-empty tuple")
        if any(not isinstance(value, SafetyCandidateItem) for value in self.items):
            raise InvalidSafetyInputError(
                "candidate items must contain only SafetyCandidateItem values"
            )
        _require_unique(
            tuple(item.exercise_code for item in self.items),
            field_name="candidate exercise codes",
        )


@dataclass(frozen=True, slots=True)
class SafetyRule:
    rule_code: str
    catalog_version_code: str
    body_area_code: BodyAreaCode
    minimum_severity_code: DiscomfortSeverityCode
    maximum_severity_code: DiscomfortSeverityCode
    effect_code: SafetyRuleEffectCode
    reason_code: str
    scope_code: SafetyRuleScopeCode
    rule_version: str
    exercise_code: str | None = None
    movement_pattern_code: str | None = None
    review_status_code: SafetyReviewStatusCode = SafetyReviewStatusCode.DOMAIN_APPROVED

    def __post_init__(self) -> None:
        _require_non_empty(self.rule_code, field_name="rule_code")
        _require_non_empty(self.catalog_version_code, field_name="catalog_version_code")
        _require_non_empty(self.reason_code, field_name="reason_code")
        _require_non_empty(self.rule_version, field_name="rule_version")
        if not isinstance(self.body_area_code, BodyAreaCode):
            raise InvalidSafetyInputError("body_area_code must be an approved BodyAreaCode")
        if not isinstance(self.minimum_severity_code, DiscomfortSeverityCode):
            raise InvalidSafetyInputError("minimum_severity_code is invalid")
        if not isinstance(self.maximum_severity_code, DiscomfortSeverityCode):
            raise InvalidSafetyInputError("maximum_severity_code is invalid")
        if self.minimum_severity_code is DiscomfortSeverityCode.NONE:
            raise InvalidSafetyInputError("safety rules cannot start at NONE severity")
        if self.minimum_severity_code > self.maximum_severity_code:
            raise InvalidSafetyInputError(
                "minimum_severity_code cannot exceed maximum_severity_code"
            )
        if not isinstance(self.effect_code, SafetyRuleEffectCode):
            raise InvalidSafetyInputError("effect_code is invalid")
        if not isinstance(self.scope_code, SafetyRuleScopeCode):
            raise InvalidSafetyInputError("scope_code is invalid")
        if not isinstance(self.review_status_code, SafetyReviewStatusCode):
            raise InvalidSafetyInputError("review_status_code is invalid")

        has_exercise = self.exercise_code is not None
        has_pattern = self.movement_pattern_code is not None
        if self.scope_code is SafetyRuleScopeCode.EXERCISE and not (
            has_exercise and not has_pattern
        ):
            raise InvalidSafetyInputError("EXERCISE scope requires only exercise_code")
        if self.scope_code is SafetyRuleScopeCode.MOVEMENT_PATTERN and not (
            has_pattern and not has_exercise
        ):
            raise InvalidSafetyInputError(
                "MOVEMENT_PATTERN scope requires only movement_pattern_code"
            )
        if self.exercise_code is not None:
            _require_non_empty(self.exercise_code, field_name="exercise_code")
        if self.movement_pattern_code is not None:
            _require_non_empty(
                self.movement_pattern_code,
                field_name="movement_pattern_code",
            )

    def applies_to(self, discomfort: Discomfort, item: SafetyCandidateItem) -> bool:
        if self.catalog_version_code != item.catalog_version_code:
            return False
        if self.body_area_code is not discomfort.body_area_code:
            return False
        if not self.minimum_severity_code <= discomfort.severity_code <= self.maximum_severity_code:
            return False
        if self.scope_code is SafetyRuleScopeCode.EXERCISE:
            return self.exercise_code == item.exercise_code
        return self.movement_pattern_code == item.movement_pattern_code

    def targets(self, body_area_code: BodyAreaCode, item: SafetyCandidateItem) -> bool:
        """Match a chronic attention area without inventing a severity.

        Chronic attention may only add caution. The record still owns the body-area,
        catalog, exercise and movement-pattern scope used to select that caution.
        """

        if self.catalog_version_code != item.catalog_version_code:
            return False
        if self.body_area_code is not body_area_code:
            return False
        if self.scope_code is SafetyRuleScopeCode.EXERCISE:
            return self.exercise_code == item.exercise_code
        return self.movement_pattern_code == item.movement_pattern_code


@dataclass(frozen=True, slots=True)
class SafetyRuleSet:
    version_code: str
    review_status_code: SafetyReviewStatusCode
    production_eligible: bool
    rules: tuple[SafetyRule, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.version_code, field_name="version_code")
        if not isinstance(self.review_status_code, SafetyReviewStatusCode):
            raise InvalidSafetyInputError("review_status_code is invalid")
        if not isinstance(self.production_eligible, bool):
            raise InvalidSafetyInputError("production_eligible must be a boolean")
        if not isinstance(self.rules, tuple) or not self.rules:
            raise InvalidSafetyInputError("rules must be a non-empty tuple")
        if any(not isinstance(value, SafetyRule) for value in self.rules):
            raise InvalidSafetyInputError("rules must contain only SafetyRule values")
        _require_unique(
            tuple(rule.rule_code for rule in self.rules),
            field_name="safety rule codes",
        )

    @property
    def availability_code(self) -> SafetyRuleAvailabilityCode:
        if self.review_status_code is not SafetyReviewStatusCode.DOMAIN_APPROVED:
            return SafetyRuleAvailabilityCode.NOT_DOMAIN_APPROVED
        if any(
            rule.review_status_code is not SafetyReviewStatusCode.DOMAIN_APPROVED
            for rule in self.rules
        ):
            return SafetyRuleAvailabilityCode.NOT_DOMAIN_APPROVED
        if not self.production_eligible:
            return SafetyRuleAvailabilityCode.NOT_PRODUCTION_ELIGIBLE
        return SafetyRuleAvailabilityCode.AVAILABLE


@dataclass(frozen=True, slots=True)
class SafetyEvaluation:
    status_code: SafetyStatusCode
    required_action_code: SafetyRequiredActionCode | None
    veto: bool
    plan_allowed: bool
    excluded_exercise_codes: tuple[str, ...]
    caution_exercise_codes: tuple[str, ...]
    applied_rule_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    emergency_reaction_codes: tuple[AdverseReactionCode, ...]
    acute_reaction_codes: tuple[AdverseReactionCode, ...]
    severe_body_area_codes: tuple[BodyAreaCode, ...]
    safety_rule_set_version: str | None
    rule_availability_code: SafetyRuleAvailabilityCode
    safety_engine_version: str = SAFETY_ENGINE_VERSION

    def __post_init__(self) -> None:
        if set(self.excluded_exercise_codes) & set(self.caution_exercise_codes):
            raise InvalidSafetyInputError("an exercise cannot be both excluded and cautioned")
        if self.excluded_exercise_codes and not self.veto:
            raise InvalidSafetyInputError("excluded exercises require a safety veto")

        if self.status_code is SafetyStatusCode.PASS:
            if not self.plan_allowed or self.veto or self.required_action_code is not None:
                raise InvalidSafetyInputError("PASS must allow the plan without a veto")
            return
        if self.plan_allowed:
            raise InvalidSafetyInputError("only PASS may allow the current plan")
        if self.status_code is SafetyStatusCode.REVISE:
            if self.required_action_code is not None:
                raise InvalidSafetyInputError("REVISE cannot require REST or STOP")
            return
        if self.status_code is SafetyStatusCode.BLOCKED:
            if not self.veto or self.required_action_code is None:
                raise InvalidSafetyInputError("BLOCKED must veto the plan and require REST or STOP")
            return
        if self.status_code in {SafetyStatusCode.NEEDS_INPUT, SafetyStatusCode.FAILED}:
            if not self.veto or self.required_action_code is not None:
                raise InvalidSafetyInputError(
                    "NEEDS_INPUT and FAILED must fail closed without a user action"
                )


def _sorted_codes[SafetyCodeT: StrEnum](
    values: AbstractSet[SafetyCodeT],
) -> tuple[SafetyCodeT, ...]:
    return tuple(sorted(values, key=str))


def _terminal_evaluation(
    *,
    action_code: SafetyRequiredActionCode,
    context: SafetyContext,
) -> SafetyEvaluation:
    emergency_codes = frozenset(context.adverse_reaction_codes) & EMERGENCY_REACTION_CODES
    acute_codes = frozenset(context.adverse_reaction_codes) & ACUTE_MUSCULOSKELETAL_REACTION_CODES
    severe_body_areas = {
        discomfort.body_area_code
        for discomfort in context.discomforts
        if discomfort.severity_code is DiscomfortSeverityCode.SEVERE
    }
    return SafetyEvaluation(
        status_code=SafetyStatusCode.BLOCKED,
        required_action_code=action_code,
        veto=True,
        plan_allowed=False,
        excluded_exercise_codes=(),
        caution_exercise_codes=(),
        applied_rule_codes=(),
        reason_codes=(),
        emergency_reaction_codes=_sorted_codes(emergency_codes),
        acute_reaction_codes=_sorted_codes(acute_codes),
        severe_body_area_codes=_sorted_codes(severe_body_areas),
        safety_rule_set_version=None,
        rule_availability_code=SafetyRuleAvailabilityCode.NOT_REQUIRED,
    )


def _rules_unavailable_evaluation(
    availability_code: SafetyRuleAvailabilityCode,
    rule_set: SafetyRuleSet | None,
) -> SafetyEvaluation:
    return SafetyEvaluation(
        status_code=SafetyStatusCode.FAILED,
        required_action_code=None,
        veto=True,
        plan_allowed=False,
        excluded_exercise_codes=(),
        caution_exercise_codes=(),
        applied_rule_codes=(),
        reason_codes=(),
        emergency_reaction_codes=(),
        acute_reaction_codes=(),
        severe_body_area_codes=(),
        safety_rule_set_version=rule_set.version_code if rule_set else None,
        rule_availability_code=availability_code,
    )


def evaluate_safety(
    context: SafetyContext,
    candidate: SafetyCandidate,
    rule_set: SafetyRuleSet | None,
) -> SafetyEvaluation:
    """Evaluate immediate stops first, then approved catalog safety rules."""

    reaction_codes = frozenset(context.adverse_reaction_codes)
    if reaction_codes & EMERGENCY_REACTION_CODES:
        return _terminal_evaluation(
            action_code=SafetyRequiredActionCode.STOP_AND_SEEK_HELP,
            context=context,
        )

    has_severe_discomfort = any(
        discomfort.severity_code is DiscomfortSeverityCode.SEVERE
        for discomfort in context.discomforts
    )
    if reaction_codes & ACUTE_MUSCULOSKELETAL_REACTION_CODES or has_severe_discomfort:
        return _terminal_evaluation(
            action_code=SafetyRequiredActionCode.REST,
            context=context,
        )

    if not context.discomforts and not context.attention_area_codes:
        return SafetyEvaluation(
            status_code=SafetyStatusCode.PASS,
            required_action_code=None,
            veto=False,
            plan_allowed=True,
            excluded_exercise_codes=(),
            caution_exercise_codes=(),
            applied_rule_codes=(),
            reason_codes=(),
            emergency_reaction_codes=(),
            acute_reaction_codes=(),
            severe_body_area_codes=(),
            safety_rule_set_version=None,
            rule_availability_code=SafetyRuleAvailabilityCode.NOT_REQUIRED,
        )

    if rule_set is None:
        return _rules_unavailable_evaluation(SafetyRuleAvailabilityCode.MISSING, None)
    if rule_set.availability_code is not SafetyRuleAvailabilityCode.AVAILABLE:
        return _rules_unavailable_evaluation(rule_set.availability_code, rule_set)

    excluded: set[str] = set()
    cautions: set[str] = set()
    applied_rules: set[str] = set()
    reasons: set[str] = set()
    for discomfort in context.discomforts:
        for item in candidate.items:
            matching_rules = [rule for rule in rule_set.rules if rule.applies_to(discomfort, item)]
            for rule in matching_rules:
                applied_rules.add(rule.rule_code)
                reasons.add(rule.reason_code)
                if rule.effect_code is SafetyRuleEffectCode.EXCLUDE:
                    excluded.add(item.exercise_code)
                elif item.exercise_code not in excluded:
                    cautions.add(item.exercise_code)

    daily_discomfort_areas = {discomfort.body_area_code for discomfort in context.discomforts}
    for attention_area_code in context.attention_area_codes:
        if attention_area_code in daily_discomfort_areas:
            continue
        for item in candidate.items:
            matching_rules = [
                rule for rule in rule_set.rules if rule.targets(attention_area_code, item)
            ]
            for rule in matching_rules:
                applied_rules.add(rule.rule_code)
                reasons.add(rule.reason_code)
                if item.exercise_code not in excluded:
                    cautions.add(item.exercise_code)

    cautions.difference_update(excluded)
    all_exercise_codes = {item.exercise_code for item in candidate.items}
    all_excluded = bool(excluded) and excluded == all_exercise_codes
    if all_excluded:
        status_code = SafetyStatusCode.BLOCKED
        required_action_code = SafetyRequiredActionCode.REST
        plan_allowed = False
        veto = True
    elif excluded or cautions:
        status_code = SafetyStatusCode.REVISE
        required_action_code = None
        plan_allowed = False
        veto = bool(excluded)
    else:
        status_code = SafetyStatusCode.PASS
        required_action_code = None
        plan_allowed = True
        veto = False

    return SafetyEvaluation(
        status_code=status_code,
        required_action_code=required_action_code,
        veto=veto,
        plan_allowed=plan_allowed,
        excluded_exercise_codes=tuple(sorted(excluded)),
        caution_exercise_codes=tuple(sorted(cautions)),
        applied_rule_codes=tuple(sorted(applied_rules)),
        reason_codes=tuple(sorted(reasons)),
        emergency_reaction_codes=(),
        acute_reaction_codes=(),
        severe_body_area_codes=(),
        safety_rule_set_version=rule_set.version_code,
        rule_availability_code=SafetyRuleAvailabilityCode.AVAILABLE,
    )
