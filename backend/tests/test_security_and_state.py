from __future__ import annotations

import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import (
    authenticate_access_token,
    consume_event_stream_ticket,
    create_event_stream_ticket,
    create_session,
    issue_access_token,
)
from app.database import Base
from app.models import UserModel
from app.services.sensitive_data import redact_sensitive
from app.services.transfer_state_machine import (
    TRANSFER_ACCEPTED_WAITING_AMBULANCE,
    TRANSFER_AMBULANCE_ASSIGNED,
    TRANSFER_COMPLETED,
    TRANSFER_PENDING_DESTINATION,
    validate_transfer_transition,
)
from app.time_utils import utcnow


class SecurityAndStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.user = UserModel(
            id="security-test-admin",
            username="security-test-admin",
            name="Security Test Admin",
            role="super_admin",
            is_active=True,
            failed_login_count=0,
        )
        self.session.add(self.user)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_claimed_user_id_without_bearer_token_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            authenticate_access_token(self.session, None)
        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail, "Authentication required")

    def test_valid_access_token_resolves_database_user(self) -> None:
        auth_session, _, _ = create_session(self.session, self.user)
        self.session.commit()
        token = issue_access_token(self.user, auth_session)
        authenticated_user, authenticated_session = authenticate_access_token(
            self.session,
            f"Bearer {token}",
        )
        self.assertEqual(authenticated_user.id, self.user.id)
        self.assertEqual(authenticated_session.id, auth_session.id)

    def test_revoked_session_invalidates_unexpired_access_token(self) -> None:
        auth_session, _, _ = create_session(self.session, self.user)
        self.session.commit()
        token = issue_access_token(self.user, auth_session)
        auth_session.revoked_at = utcnow()
        self.session.commit()
        with self.assertRaises(HTTPException) as context:
            authenticate_access_token(self.session, f"Bearer {token}")
        self.assertEqual(context.exception.status_code, 401)

    def test_event_stream_ticket_can_only_be_consumed_once(self) -> None:
        ticket = create_event_stream_ticket(self.session, self.user)
        self.session.commit()
        self.assertEqual(consume_event_stream_ticket(self.session, ticket).id, self.user.id)
        with self.assertRaises(HTTPException) as context:
            consume_event_stream_ticket(self.session, ticket)
        self.assertEqual(context.exception.status_code, 401)

    def test_valid_transfer_transition_is_allowed(self) -> None:
        validate_transfer_transition(
            TRANSFER_PENDING_DESTINATION,
            TRANSFER_ACCEPTED_WAITING_AMBULANCE,
        )

    def test_invalid_transfer_completion_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            validate_transfer_transition(
                TRANSFER_PENDING_DESTINATION,
                TRANSFER_COMPLETED,
            )
        self.assertEqual(context.exception.status_code, 409)

    def test_dispatch_after_completion_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            validate_transfer_transition(
                TRANSFER_COMPLETED,
                TRANSFER_AMBULANCE_ASSIGNED,
            )
        self.assertEqual(context.exception.status_code, 409)

    def test_sensitive_audit_details_are_redacted_recursively(self) -> None:
        payload = {
            "origin_hospital_id": "1",
            "patient_name": "Nimal Perera",
            "clinical": {
                "diagnosis": "respiratory failure",
                "urgency_class": "critical",
            },
            "candidate_rankings": [
                {"ambulance_id": "AMB-001", "score": 1.2},
            ],
        }
        redacted = redact_sensitive(payload)
        self.assertEqual(redacted["patient_name"], "[REDACTED]")
        self.assertEqual(redacted["clinical"]["diagnosis"], "[REDACTED]")
        self.assertEqual(redacted["clinical"]["urgency_class"], "critical")
        self.assertEqual(redacted["candidate_rankings"][0]["ambulance_id"], "AMB-001")


if __name__ == "__main__":
    unittest.main()
