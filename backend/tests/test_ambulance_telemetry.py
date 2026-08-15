from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import ambulance as ambulance_routes
from app.auth import create_event_stream_ticket
from app.database import Base
from app.main import app
from app.models import AmbulanceModel, HospitalModel, UserModel


class AmbulanceTelemetryStreamTests(unittest.TestCase):
    """Cover the telemetry WebSocket end to end.

    The first payload this stream sends is assembled from several helpers, so a
    signature mismatch in any of them only surfaces once a client actually
    connects. Exercising a real connection keeps that failure mode visible.
    """

    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

        with self.session_factory() as db:
            db.add(
                HospitalModel(
                    id="1",
                    name="Telemetry Test Hospital",
                    latitude=6.9271,
                    longitude=79.8612,
                    icu_type="general",
                    total_beds=4,
                    occupied_beds=0,
                )
            )
            db.add(
                AmbulanceModel(
                    id="AMB-TELEMETRY",
                    call_sign="TEL-1",
                    base_hospital_id="1",
                    status="available",
                    latitude=6.9271,
                    longitude=79.8612,
                )
            )
            db.add(
                UserModel(
                    id="telemetry-crew",
                    username="telemetry-crew",
                    name="Telemetry Crew",
                    role="ambulance_crew",
                    ambulance_id="AMB-TELEMETRY",
                    is_active=True,
                    failed_login_count=0,
                )
            )
            db.commit()

        self.patcher = patch.object(ambulance_routes, "SessionLocal", self.session_factory)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.engine.dispose()

    def _issue_ticket(self) -> str:
        with self.session_factory() as db:
            user = db.get(UserModel, "telemetry-crew")
            ticket = create_event_stream_ticket(db, user)
            db.commit()
        return ticket

    def test_stream_sends_ambulance_payload_to_authenticated_crew(self) -> None:
        ticket = self._issue_ticket()
        # Deliberately not used as a context manager: entering it would run the
        # app lifespan, which seeds the real development database and starts the
        # fleet simulation thread. The routes under test need neither.
        client = TestClient(app)
        with client.websocket_connect(f"/api/ambulance/telemetry?ticket={ticket}") as websocket:
            message = websocket.receive_json()

        self.assertEqual(message["kind"], "ambulance_telemetry")
        self.assertEqual(message["ambulance"]["id"], "AMB-TELEMETRY")
        self.assertEqual(message["ambulance"]["call_sign"], "TEL-1")
        self.assertIsNone(message["active_transfer_id"])
        self.assertIn("server_time", message)

    def test_stream_rejects_an_invalid_ticket(self) -> None:
        client = TestClient(app)
        with client.websocket_connect("/api/ambulance/telemetry?ticket=not-a-real-ticket") as websocket:
            with self.assertRaises(Exception):
                websocket.receive_json()


if __name__ == "__main__":
    unittest.main()
