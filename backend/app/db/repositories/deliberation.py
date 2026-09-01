import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.decision import (
    AgentProposalRecord,
    AgentProposalRevisionRecord,
    AgentReviewEventRecord,
    DecisionDeliberationRecord,
    DecisionRun,
)

_AGENT_TYPE_CODES = ("TRAINING", "RECOVERY", "SAFETY", "FEASIBILITY")
_AGENT_TYPE_SET = frozenset(_AGENT_TYPE_CODES)


def canonical_payload_hash(payload: object) -> str:
    """Hash a JSON-compatible payload using the V2 canonical representation."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ProposalReferenceWrite:
    agent_type_code: str
    proposal_hash: str


@dataclass(frozen=True)
class RevisedProposalWrite:
    proposal_status_code: str
    proposal_schema_version: str
    proposal_payload: dict[str, Any]


@dataclass(frozen=True)
class ReviewEventWrite:
    agent_type_code: str
    review_status_code: str
    revision_status_code: str | None
    review_schema_version: str
    reviewed_proposal_references: tuple[ProposalReferenceWrite, ...]
    review_payload: dict[str, Any]
    revised_proposal: RevisedProposalWrite | None = None


class DeliberationRepository:
    """Persist one complete, validated V2 deliberation as an additive graph."""

    def persist(
        self,
        session: Session,
        *,
        decision_run_id: UUID,
        deliberation_schema_version: str,
        round_count: int,
        round_two_status_code: str,
        conflict_detector_version: str,
        precedence_version: str,
        conflict_codes: tuple[str, ...],
        reviews: tuple[ReviewEventWrite, ...],
        now: datetime,
    ) -> UUID:
        run = session.get(DecisionRun, decision_run_id)
        if run is None:
            raise ValueError("decision run does not exist")
        if session.scalar(
            select(DecisionDeliberationRecord.id).where(
                DecisionDeliberationRecord.decision_run_id == decision_run_id
            )
        ):
            raise ValueError("decision deliberation already exists")

        canonical_conflict_codes = tuple(sorted(set(conflict_codes)))
        if canonical_conflict_codes != conflict_codes:
            raise ValueError("conflict codes must be unique and in canonical order")
        reviews_by_agent = self._reviews_by_agent(reviews)

        proposals = tuple(
            session.scalars(
                select(AgentProposalRecord)
                .where(AgentProposalRecord.decision_run_id == decision_run_id)
                .order_by(AgentProposalRecord.agent_type_code)
            )
        )
        proposals_by_agent = {proposal.agent_type_code: proposal for proposal in proposals}
        if set(proposals_by_agent) != _AGENT_TYPE_SET or len(proposals) != len(_AGENT_TYPE_CODES):
            raise ValueError("V2 deliberation requires exactly four Round 1 proposals")

        conflict_payload = {
            "conflict_codes": list(canonical_conflict_codes),
            "conflict_detector_version": conflict_detector_version,
            "precedence_version": precedence_version,
        }
        deliberation = DecisionDeliberationRecord(
            id=uuid4(),
            decision_run_id=decision_run_id,
            policy_version_id=run.policy_version_id,
            deliberation_schema_version=deliberation_schema_version,
            graph_version=run.graph_version,
            round_count=round_count,
            round_two_status_code=round_two_status_code,
            conflict_detector_version=conflict_detector_version,
            precedence_version=precedence_version,
            conflict_codes=list(canonical_conflict_codes),
            conflict_hash=canonical_payload_hash(conflict_payload),
            created_at=now,
        )
        session.add(deliberation)
        session.flush()

        baselines: dict[str, AgentProposalRevisionRecord] = {}
        for agent_type_code in _AGENT_TYPE_CODES:
            proposal = proposals_by_agent[agent_type_code]
            baseline = AgentProposalRevisionRecord(
                id=uuid4(),
                decision_run_id=decision_run_id,
                deliberation_id=deliberation.id,
                source_proposal_id=proposal.id,
                baseline_revision_id=None,
                policy_version_id=run.policy_version_id,
                round_number=1,
                agent_type_code=agent_type_code,
                proposal_status_code=proposal.proposal_status_code,
                proposal_schema_version=proposal.schema_version,
                proposal_payload=proposal.proposal_payload,
                proposal_hash=canonical_payload_hash(proposal.proposal_payload),
                created_at=now,
            )
            session.add(baseline)
            baselines[agent_type_code] = baseline
        session.flush()

        for agent_type_code in _AGENT_TYPE_CODES:
            review = reviews_by_agent[agent_type_code]
            baseline = baselines[agent_type_code]
            references = self._canonical_references(review, baselines)
            revised = self._persist_revised_proposal(
                session,
                run,
                deliberation,
                baseline,
                review,
                now,
            )
            review_envelope = {
                "agent_type_code": agent_type_code,
                "baseline_proposal_hash": baseline.proposal_hash,
                "review_payload": review.review_payload,
                "review_schema_version": review.review_schema_version,
                "review_status_code": review.review_status_code,
                "reviewed_proposal_references": references,
                "revised_proposal_hash": revised.proposal_hash if revised else None,
                "revision_status_code": review.revision_status_code,
                "round_number": 2,
            }
            session.add(
                AgentReviewEventRecord(
                    id=uuid4(),
                    decision_run_id=decision_run_id,
                    deliberation_id=deliberation.id,
                    baseline_revision_id=baseline.id,
                    revised_revision_id=revised.id if revised else None,
                    round_number=2,
                    agent_type_code=agent_type_code,
                    review_status_code=review.review_status_code,
                    revision_status_code=review.revision_status_code,
                    review_schema_version=review.review_schema_version,
                    baseline_proposal_hash=baseline.proposal_hash,
                    reviewed_proposal_references=references,
                    review_payload=review.review_payload,
                    review_hash=canonical_payload_hash(review_envelope),
                    created_at=now,
                )
            )
        session.flush()
        return deliberation.id

    @staticmethod
    def _reviews_by_agent(
        reviews: tuple[ReviewEventWrite, ...],
    ) -> dict[str, ReviewEventWrite]:
        reviews_by_agent = {review.agent_type_code: review for review in reviews}
        if set(reviews_by_agent) != _AGENT_TYPE_SET or len(reviews) != len(_AGENT_TYPE_CODES):
            raise ValueError("V2 deliberation requires exactly four Round 2 review events")
        return reviews_by_agent

    @staticmethod
    def _canonical_references(
        review: ReviewEventWrite,
        baselines: dict[str, AgentProposalRevisionRecord],
    ) -> list[dict[str, str]]:
        provided = tuple(
            (reference.agent_type_code, reference.proposal_hash)
            for reference in review.reviewed_proposal_references
        )
        canonical = tuple(sorted(set(provided)))
        if provided != canonical:
            raise ValueError("reviewed proposal references must be unique and canonical")
        for agent_type_code, proposal_hash in canonical:
            baseline = baselines.get(agent_type_code)
            if baseline is None or baseline.proposal_hash != proposal_hash:
                raise ValueError("reviewed proposal reference does not match Round 1")
        return [
            {"agent_type_code": agent_type_code, "proposal_hash": proposal_hash}
            for agent_type_code, proposal_hash in canonical
        ]

    @staticmethod
    def _persist_revised_proposal(
        session: Session,
        run: DecisionRun,
        deliberation: DecisionDeliberationRecord,
        baseline: AgentProposalRevisionRecord,
        review: ReviewEventWrite,
        now: datetime,
    ) -> AgentProposalRevisionRecord | None:
        if (review.revision_status_code == "REVISED") != (review.revised_proposal is not None):
            raise ValueError("REVISED review status and revised proposal must appear together")
        if review.revised_proposal is None:
            return None
        revised = review.revised_proposal
        record = AgentProposalRevisionRecord(
            id=uuid4(),
            decision_run_id=run.id,
            deliberation_id=deliberation.id,
            source_proposal_id=None,
            baseline_revision_id=baseline.id,
            policy_version_id=run.policy_version_id,
            round_number=2,
            agent_type_code=review.agent_type_code,
            proposal_status_code=revised.proposal_status_code,
            proposal_schema_version=revised.proposal_schema_version,
            proposal_payload=revised.proposal_payload,
            proposal_hash=canonical_payload_hash(revised.proposal_payload),
            created_at=now,
        )
        session.add(record)
        session.flush()
        return record


__all__ = [
    "DeliberationRepository",
    "ProposalReferenceWrite",
    "RevisedProposalWrite",
    "ReviewEventWrite",
    "canonical_payload_hash",
]
