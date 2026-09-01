from src.approval_workflow import determine_approval_status
from src.schemas import ApprovalStatus


def test_high_confidence_auto_approves():
    assert determine_approval_status(0.95) == ApprovalStatus.AUTO_APPROVED


def test_low_confidence_routes_to_review():
    assert determine_approval_status(0.72) == ApprovalStatus.PENDING_REVIEW


def test_exactly_at_threshold_auto_approves():
    # >= threshold, not >, so exactly 90% is treated as sufficient
    assert determine_approval_status(0.90) == ApprovalStatus.AUTO_APPROVED


def test_just_below_threshold_routes_to_review():
    assert determine_approval_status(0.899) == ApprovalStatus.PENDING_REVIEW


def test_custom_threshold_respected():
    # A stricter deployment (e.g. credit risk) might require 98% confidence
    assert determine_approval_status(0.95, threshold=0.98) == ApprovalStatus.PENDING_REVIEW
    assert determine_approval_status(0.99, threshold=0.98) == ApprovalStatus.AUTO_APPROVED


def test_zero_and_full_confidence_edge_cases():
    assert determine_approval_status(0.0) == ApprovalStatus.PENDING_REVIEW
    assert determine_approval_status(1.0) == ApprovalStatus.AUTO_APPROVED
