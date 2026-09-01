"""
Human-in-the-loop approval workflow.

Banks and consulting firms don't let an AI system's recommendation reach
a decision-maker unreviewed - especially in a regulated context like
M&A due diligence or credit risk. This module implements the routing
rule: high-confidence reports auto-approve, everything else is queued
for a human reviewer, whose decision (and any edits) is captured for
future prompt/model improvement.

This is deliberately NOT an online-learning loop - no weights update
from reviewer feedback in this codebase. What's real: every reviewer
edit is persisted (`FeedbackRecord` in db.py) as labeled training data
a future iteration could use for prompt refinement or fine-tuning. Say
that distinction directly if asked "does it learn from feedback" - the
data pipeline for learning exists, the learning itself doesn't (yet).
"""

from __future__ import annotations

from .schemas import ApprovalStatus

DEFAULT_CONFIDENCE_THRESHOLD = 0.90


def determine_approval_status(
    confidence_score: float, threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
) -> ApprovalStatus:
    """
    Routes a report based on its confidence score.

    >= threshold -> auto-approved, no human review needed
    <  threshold -> pending_review, held for a human reviewer

    Threshold is a parameter, not a hardcoded constant, since different
    deployments (e.g. a stricter credit-risk workflow vs. a looser
    internal research tool) may reasonably want a different bar.
    """
    if confidence_score >= threshold:
        return ApprovalStatus.AUTO_APPROVED
    return ApprovalStatus.PENDING_REVIEW
