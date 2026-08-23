from fastapi.testclient import TestClient

from app.main import create_app
from app.services.boot_jobs import ActiveBootJobError, BootJobNotCancellableError


AUTH_HEADERS = {"Tailscale-User-Login": "tester@example.com"}
JOB = {
    "id": "job-1",
    "target": "mainpc",
    "state": "queued",
    "stage": "queued",
    "terminal": False,
    "can_cancel": True,
    "created_at": "2026-08-23T00:00:00+00:00",
    "updated_at": "2026-08-23T00:00:00+00:00",
    "error_code": None,
}


class FakeBootJobs:
    def __init__(self):
        self.actor = None

    def create_job(self, target, actor):
        self.actor = actor
        return {**JOB, "target": target}

    def list_jobs(self, target=None, limit=20):
        return [{**JOB, "target": target or "mainpc"}]

    def get_job(self, _job_id):
        return JOB

    def cancel_job(self, _job_id):
        return {**JOB, "state": "cancelled", "stage": "cancelled", "terminal": True, "can_cancel": False}


def make_client(fake=None):
    app = create_app()
    app.state.boot_jobs = fake or FakeBootJobs()
    return TestClient(app), app.state.boot_jobs


def test_create_boot_job_returns_202_and_uses_identity():
    client, fake = make_client()
    response = client.post("/api/boot/ubuntu", headers=AUTH_HEADERS, json={"target": "mainpc"})
    assert response.status_code == 202
    assert response.json()["job"]["id"] == "job-1"
    assert fake.actor == "tester@example.com"


def test_jobs_can_be_listed_retrieved_and_cancelled():
    client, _fake = make_client()
    listed = client.get("/api/jobs?target=mainpc", headers=AUTH_HEADERS)
    fetched = client.get("/api/jobs/job-1", headers=AUTH_HEADERS)
    cancelled = client.post("/api/jobs/job-1/cancel", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert fetched.json()["job"]["id"] == "job-1"
    assert cancelled.json()["job"]["state"] == "cancelled"


def test_duplicate_job_returns_409_with_active_job():
    class ConflictBootJobs(FakeBootJobs):
        def create_job(self, _target, _actor):
            raise ActiveBootJobError(JOB)

    client, _fake = make_client(ConflictBootJobs())
    response = client.post("/api/boot/ubuntu", headers=AUTH_HEADERS, json={"target": "mainpc"})
    assert response.status_code == 409
    assert response.json()["detail"]["job"]["id"] == "job-1"


def test_non_cancellable_job_returns_409():
    class NonCancellableBootJobs(FakeBootJobs):
        def cancel_job(self, _job_id):
            raise BootJobNotCancellableError()

    client, _fake = make_client(NonCancellableBootJobs())
    response = client.post("/api/jobs/job-1/cancel", headers=AUTH_HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "job_not_cancellable"
