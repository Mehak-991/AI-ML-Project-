"""Regression tests for the production-readiness audit: every test pins a confirmed bug."""

import subprocess
import time
import uuid
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core import security
from app.core.exceptions import TrainingError
from app.core.middleware import RateLimitMiddleware
from app.database.models import Job
from app.database.models.experiment import Experiment
from app.database.models.user import RefreshToken, User
from app.database.session import get_db
from app.main import create_app
from app.ml.synthetic import make_classification_frame
from app.schemas.experiment import ExperimentCreate
from app.services import experiment_service, explainability_service, job_service
from scripts import restore_db
from tests.helpers import insert_account, to_csv_bytes

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd"
RECORD = {"num_a": 1.0, "num_b": 0.2, "num_c": 3, "cat_a": "red", "cat_b": "small"}


@pytest.fixture
def secure_client(make_settings, session_factory):
    app = create_app(make_settings(APP_ENV="testing", RATE_LIMIT_ENABLED=False))

    def _get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _login(client, email: str) -> dict:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def _bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def actors(secure_client, session_factory) -> dict:
    """admin = superadmin; owner = admin (owns the created resources); other and viewer = users.

    Privileged accounts are created out of band, as the server-side bootstrap would; public
    registration can only create a read-only user.
    """
    c = secure_client
    for email, role in (
        ("root@x.com", "superadmin"),
        ("a@x.com", "admin"),
        ("b@x.com", "user"),
        ("v@x.com", "user"),
    ):
        insert_account(session_factory, email, role, PASSWORD)
    return {
        "admin": _login(c, "root@x.com"),
        "owner": _login(c, "a@x.com"),
        "other": _login(c, "b@x.com"),
        "viewer": _login(c, "v@x.com"),
    }


@pytest.fixture
def owned(secure_client, actors) -> dict:
    """A dataset, model, deployment and experiment belonging to the 'owner' actor."""
    headers = _bearer(actors["owner"])
    frame = make_classification_frame(120)
    dataset = secure_client.post(
        f"{API}/datasets", files={"file": ("d.csv", to_csv_bytes(frame))}, headers=headers
    )
    assert dataset.status_code == 201, dataset.text
    dataset_id = dataset.json()["dataset"]["id"]
    model = secure_client.post(
        f"{API}/models/train",
        json={"dataset_id": dataset_id, "target_column": "label", "name": "owned"},
        headers=headers,
    )
    assert model.status_code == 201, model.text
    deployment = secure_client.post(
        f"{API}/models/{model.json()['id']}/deploy",
        json={},
        headers=_bearer(actors["admin"]),
    )
    assert deployment.status_code == 200, deployment.text
    experiment = secure_client.post(
        f"{API}/experiments",
        json={
            "name": "owned-exp",
            "dataset_id": dataset_id,
            "target_column": "label",
            "problem_type": "classification",
            "algorithm": "linear",
        },
        headers=headers,
    )
    assert experiment.status_code == 201, experiment.text
    return {
        "dataset": dataset_id,
        "model": model.json()["id"],
        "deployment": deployment.json()["id"],
        "experiment": experiment.json()["id"],
    }


# --- missing authentication --------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", f"{API}/deployments"),
        ("get", f"{API}/deployments/{uuid.uuid4()}"),
        ("get", f"{API}/drift/overview"),
        ("get", f"{API}/drift/alerts"),
        ("get", f"{API}/drift/models/{uuid.uuid4()}/reports"),
        ("get", f"{API}/drift/models/{uuid.uuid4()}/alerts"),
    ],
)
def test_previously_public_routes_require_authentication(secure_client, method, path) -> None:
    assert getattr(secure_client, method)(path).status_code == 401


def test_dataset_validation_requires_an_uploader_role(secure_client, actors) -> None:
    files = {"file": ("d.csv", to_csv_bytes(make_classification_frame(30)))}
    assert secure_client.post(f"{API}/datasets/validate", files=files).status_code == 401
    denied = secure_client.post(
        f"{API}/datasets/validate", files=files, headers=_bearer(actors["viewer"])
    )
    assert denied.status_code == 403
    allowed = secure_client.post(
        f"{API}/datasets/validate", files=files, headers=_bearer(actors["owner"])
    )
    assert allowed.status_code == 200, allowed.text


# --- object-level authorization ----------------------------------------------------------


def test_other_users_cannot_reach_owned_objects(secure_client, actors, owned) -> None:
    other = _bearer(actors["other"])
    denied = [
        ("get", f"{API}/datasets/{owned['dataset']}", None),
        ("get", f"{API}/datasets/{owned['dataset']}/summary", None),
        ("get", f"{API}/datasets/{owned['dataset']}/preview", None),
        ("get", f"{API}/deployments?model_id={owned['model']}", None),
        ("get", f"{API}/deployments/{owned['deployment']}", None),
        ("get", f"{API}/monitoring/models/{owned['model']}", None),
        ("get", f"{API}/models/{owned['model']}/explainability/summary", None),
        ("get", f"{API}/drift/models/{owned['model']}/reports", None),
        ("get", f"{API}/drift/models/{owned['model']}/alerts", None),
        ("post", f"{API}/drift/models/{owned['model']}/analyze-quality", None),
        ("post", f"{API}/drift/models/{owned['model']}/analyze-performance", None),
        ("get", f"{API}/experiments/{owned['experiment']}", None),
        ("post", f"{API}/experiments/{owned['experiment']}/run", None),
        ("post", f"{API}/experiments/{owned['experiment']}/rerun", None),
        ("post", f"{API}/experiments/{owned['experiment']}/cancel", None),
        ("get", f"{API}/experiments/compare?experiment_ids={owned['experiment']}", None),
        (
            "post",
            f"{API}/models/train",
            {"dataset_id": owned["dataset"], "target_column": "label"},
        ),
        (
            "post",
            f"{API}/experiments",
            {
                "name": "steal",
                "dataset_id": owned["dataset"],
                "target_column": "label",
                "problem_type": "classification",
                "algorithm": "linear",
            },
        ),
        (
            "post",
            f"{API}/jobs",
            {"job_type": "experiment_execution", "experiment_id": owned["experiment"]},
        ),
        (
            "post",
            f"{API}/jobs",
            {
                "job_type": "model_training",
                "input_config": {"dataset_id": owned["dataset"], "target_column": "label"},
            },
        ),
    ]
    for method, path, body in denied:
        kwargs = {"json": body} if body is not None else {}
        response = getattr(secure_client, method)(path, headers=other, **kwargs)
        assert response.status_code == 403, (path, response.status_code, response.text)


def test_listings_are_scoped_to_the_caller(secure_client, actors, owned) -> None:
    for path, key in (
        (f"{API}/datasets", "dataset"),
        (f"{API}/deployments", "deployment"),
        (f"{API}/experiments", "experiment"),
    ):
        as_other = secure_client.get(path, headers=_bearer(actors["other"])).json()
        assert as_other["total"] == 0, path
        assert as_other["items"] == [], path
        as_owner = secure_client.get(path, headers=_bearer(actors["owner"])).json()
        assert [item["id"] for item in as_owner["items"]] == [owned[key]], path
        as_admin = secure_client.get(path, headers=_bearer(actors["admin"])).json()
        assert as_admin["total"] == 1, path

    overview = secure_client.get(f"{API}/drift/overview", headers=_bearer(actors["other"]))
    assert overview.status_code == 200
    assert overview.json()["models"] == []


def test_legacy_unowned_datasets_stay_visible(secure_client, actors, session_factory, owned) -> None:
    from app.database.models import Dataset

    with session_factory() as session:
        session.get(Dataset, uuid.UUID(owned["dataset"])).owner_id = None
        session.commit()
    response = secure_client.get(
        f"{API}/datasets/{owned['dataset']}", headers=_bearer(actors["viewer"])
    )
    assert response.status_code == 200


# --- tokens ----------------------------------------------------------------------------


def test_replayed_refresh_token_ends_all_sessions(secure_client, actors) -> None:
    tokens = actors["owner"]
    second_session = _login(secure_client, "a@x.com")
    rotated = secure_client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    replay = secure_client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401
    for session in (rotated.json(), second_session):
        response = secure_client.post(
            f"{API}/auth/refresh", json={"refresh_token": session["refresh_token"]}
        )
        assert response.status_code == 401


def test_concurrent_refresh_loser_gets_rejected(db_session: Session, make_settings) -> None:
    """The conditional UPDATE decides the winner even if both requests read revoked=False."""
    from app.schemas.auth import RefreshTokenRequest
    from app.services import auth_service

    settings = make_settings(APP_ENV="testing")
    user = User(email="r@x.com", hashed_password="x", full_name="", role="user", is_active=True)
    db_session.add(user)
    db_session.flush()
    raw, token_hash = security.generate_refresh_token()
    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at="2999-01-01T00:00:00+00:00",
            revoked=False,
        )
    )
    db_session.commit()
    # Simulates the other request committing between our read and our update.
    from sqlalchemy import update

    original_get = auth_service.RefreshTokenRepository.get_by_hash

    def racing_get(self, value):
        record = original_get(self, value)
        self.session.execute(update(RefreshToken).values(revoked=True))
        self.session.commit()
        record.revoked = False  # what the losing request saw
        return record

    with (
        patch.object(auth_service.RefreshTokenRepository, "get_by_hash", racing_get),
        pytest.raises(auth_service.AuthenticationError),
    ):
        auth_service.refresh_access_token(
            db_session, settings, RefreshTokenRequest(refresh_token=raw)
        )
    assert db_session.scalar(select(func.count()).select_from(RefreshToken)) == 1


def test_database_outage_during_auth_is_503_not_401(make_settings) -> None:
    app = create_app(make_settings(APP_ENV="testing"))
    token = security.create_access_token({"sub": str(uuid.uuid4())}, app.state.ai.settings)
    broken = MagicMock(spec=Session)
    broken.get.side_effect = OperationalError("SELECT 1", {}, Exception("server closed"))
    app.dependency_overrides[get_db] = lambda: broken
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503


def test_auth_lookup_releases_its_database_connection(session_factory, make_settings) -> None:
    """The auth session is separate from the route's; it must not pin a second connection."""
    from fastapi.security import HTTPAuthorizationCredentials

    from app.api.deps import get_current_user

    settings = make_settings(APP_ENV="testing", JWT_SECRET_KEY="k" * 48)
    with session_factory() as session:
        user = User(email="c@x.com", hashed_password="x", full_name="n", role="user", is_active=True)
        session.add(user)
        session.commit()
        user_id = user.id
    token = security.create_access_token({"sub": str(user_id)}, settings)
    with session_factory() as session:
        found = get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), session, settings
        )
        assert not session.in_transaction()
        assert found.full_name == "n"  # still readable without a new query


def test_tokens_without_expiry_or_subject_are_rejected(make_settings) -> None:
    import jwt

    settings = make_settings(APP_ENV="testing", JWT_SECRET_KEY="k" * 48)
    secret = settings.JWT_SECRET_KEY.get_secret_value()
    for claims in ({"sub": "x", "type": "access"}, {"exp": 9999999999, "type": "access"}):
        with pytest.raises(jwt.PyJWTError):
            security.decode_access_token(jwt.encode(claims, secret, "HS256"), settings)
    wrong_type = jwt.encode({"sub": "x", "exp": 9999999999, "type": "refresh"}, secret, "HS256")
    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token(wrong_type, settings)


def test_login_spends_password_work_for_unknown_emails(secure_client) -> None:
    with patch.object(security, "verify_and_rehash", wraps=security.verify_and_rehash) as spy:
        response = secure_client.post(
            f"{API}/auth/login", json={"email": "nobody@x.com", "password": PASSWORD}
        )
    assert response.status_code == 401
    spy.assert_called_once()
    assert spy.call_args.args[1] is None, "unknown account: no stored hash, dummy work only"


def test_oversized_login_password_is_a_validation_error(secure_client) -> None:
    response = secure_client.post(
        f"{API}/auth/login", json={"email": "a@x.com", "password": "x" * 5000}
    )
    assert response.status_code == 422


# --- configuration -----------------------------------------------------------------------


def test_database_echo_refused_in_production(make_settings) -> None:
    with pytest.raises(ValueError, match="DATABASE_ECHO"):
        make_settings(
            APP_ENV="production",
            DATABASE_URL="postgresql://u:p@h/d",
            JWT_SECRET_KEY="s" * 48,
            DATABASE_ECHO=True,
        )


def test_non_hmac_jwt_algorithms_are_rejected(make_settings) -> None:
    for algorithm in ("none", "RS256"):
        with pytest.raises(ValueError):
            make_settings(JWT_ALGORITHM=algorithm)


def test_metrics_token_is_enforced_when_configured(make_settings, session_factory) -> None:
    app = create_app(make_settings(APP_ENV="testing", METRICS_TOKEN="scrape-me"))
    app.dependency_overrides[get_db] = lambda: session_factory()
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/metrics").status_code == 401
        bad = client.get("/metrics", headers={"Authorization": "Bearer wrong"})
        assert bad.status_code == 401
        good = client.get("/metrics", headers={"Authorization": "Bearer scrape-me"})
        assert good.status_code == 200


def test_metrics_read_the_configured_heartbeat_file(make_settings, session_factory, tmp_path) -> None:
    heartbeat = tmp_path / "beat"
    heartbeat.write_text(str(time.time()), encoding="utf-8")
    app = create_app(make_settings(APP_ENV="testing", WORKER_HEARTBEAT_FILE=str(heartbeat)))
    app.dependency_overrides[get_db] = lambda: session_factory()
    with TestClient(app, raise_server_exceptions=False) as client:
        body = client.get("/metrics").text
    assert "aiml_worker_health_status 1" in body


def test_expensive_ml_routes_have_their_own_rate_budgets() -> None:
    limiter = RateLimitMiddleware(
        MagicMock(),
        api_prefix=API,
        default_per_minute=300,
        ai_per_minute=30,
        training_per_minute=10,
        analysis_per_minute=60,
    )
    model = uuid.uuid4()
    for path in (f"{API}/experiments/{model}/run", f"{API}/experiments/{model}/rerun"):
        assert limiter.rule_for("POST", path).name == "training", path
    for path in (
        f"{API}/jobs",
        f"{API}/models/{model}/explainability/shap",
        f"{API}/models/{model}/explainability/lime",
        f"{API}/drift/models/{model}/analyze-drift",
    ):
        assert limiter.rule_for("POST", path).name == "analysis", path
    assert limiter.rule_for("GET", f"{API}/jobs").name == "default"
    assert limiter.rule_for("GET", f"{API}/models/{model}/explainability/summary").name == "default"


# --- jobs --------------------------------------------------------------------------------


def _job_user(session: Session) -> User:
    user = User(email=f"{uuid.uuid4().hex}@x.com", hashed_password="x", full_name="", role="admin")
    session.add(user)
    session.commit()
    return user


def _run_job(session_factory, make_settings, job_id) -> Job:
    settings = make_settings(APP_ENV="testing")
    with (
        patch.object(job_service, "get_session_factory", return_value=session_factory),
        patch.object(job_service, "_still_owns", return_value=True),
    ):
        job_service._execute_worker_task(job_id, settings)
    with session_factory() as session:
        return session.get(Job, job_id)


@pytest.mark.parametrize(
    ("job_type", "missing"),
    [
        ("batch_prediction", "model_id"),
        ("drift_analysis", "model_id"),
        ("explainability", "model_id"),
        ("experiment_execution", "experiment_id"),
    ],
)
def test_job_without_required_target_fails_instead_of_faking_success(
    session_factory, make_settings, job_type, missing
) -> None:
    with session_factory() as session:
        job = job_service.create_job(session, job_type, _job_user(session), input_config={})
        job_id = job.id
    finished = _run_job(session_factory, make_settings, job_id)
    assert finished.status == "failed"
    assert missing in finished.error_message
    assert finished.result is None


def test_failed_experiment_run_fails_the_job(session_factory, make_settings) -> None:
    with session_factory() as session:
        user = _job_user(session)
        experiment = Experiment(
            name="e",
            dataset_id=uuid.uuid4(),
            target_column="t",
            problem_type="classification",
            algorithm="linear",
        )
        session.add(experiment)
        session.commit()
        job = job_service.create_job(
            session, "experiment_execution", user, input_config={}, experiment_id=experiment.id
        )
        job_id = job.id
    failed_run = MagicMock(status="failed", error_message="boom")
    with patch.object(experiment_service, "execute_pipeline_run", return_value=failed_run):
        finished = _run_job(session_factory, make_settings, job_id)
    assert finished.status == "failed"
    assert "boom" in finished.error_message


def test_long_error_messages_fit_the_current_stage_column(session_factory, make_settings) -> None:
    """VARCHAR(128) on PostgreSQL: an unbounded stage left the job stuck in 'running'."""
    with session_factory() as session:
        job = Job(
            job_type="model_training",
            status="queued",
            created_by_id=_job_user(session).id,
            input_config={"dataset_id": str(uuid.uuid4()), "target_column": "t"},
            max_retries=1,
        )
        session.add(job)
        session.commit()
        job_id = job.id
    with patch("app.services.model_service.train", side_effect=RuntimeError("x" * 5000)):
        finished = _run_job(session_factory, make_settings, job_id)
    assert finished.status == "retry_pending"
    assert len(finished.current_stage) <= job_service.MAX_STAGE_LENGTH
    assert len(finished.error_message) <= 1000


def test_client_errors_are_not_retried(session_factory, make_settings) -> None:
    with session_factory() as session:
        job = Job(
            job_type="model_training",
            status="queued",
            created_by_id=_job_user(session).id,
            input_config={"dataset_id": str(uuid.uuid4()), "target_column": "t"},
            max_retries=3,
        )
        session.add(job)
        session.commit()
        job_id = job.id
    with patch("app.services.model_service.train", side_effect=TrainingError("bad data")):
        finished = _run_job(session_factory, make_settings, job_id)
    assert finished.status == "failed"


def test_invalid_training_config_is_a_permanent_failure(session_factory, make_settings) -> None:
    with session_factory() as session:
        job = job_service.create_job(
            session, "model_training", _job_user(session), input_config={"nonsense": True}
        )
        job_id = job.id
    assert _run_job(session_factory, make_settings, job_id).status == "failed"


def test_worker_mode_leaves_jobs_for_the_standalone_worker(make_settings) -> None:
    with patch.object(job_service, "dispatch_job") as dispatch:
        job_service.dispatch_if_inline(uuid.uuid4(), make_settings(JOB_INLINE_DISPATCH=False))
        dispatch.assert_not_called()
        job_service.dispatch_if_inline(uuid.uuid4(), make_settings(JOB_INLINE_DISPATCH=True))
        dispatch.assert_called_once()


def test_manual_retry_clears_previous_outcome(session_factory, make_settings) -> None:
    from datetime import UTC, datetime

    with session_factory() as session:
        user = _job_user(session)
        job = Job(
            job_type="batch_prediction",
            status="failed",
            created_by_id=user.id,
            input_config={},
            completed_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            execution_duration_seconds=3.0,
            error_message="old",
        )
        session.add(job)
        session.commit()
        retried = job_service.retry_job(
            session, make_settings(JOB_INLINE_DISPATCH=False), job.id, user
        )
        assert retried.status == "queued"
        assert retried.completed_at is None
        assert retried.started_at is None
        assert retried.execution_duration_seconds is None


# --- experiments -------------------------------------------------------------------------


@pytest.fixture
def owner_experiment_payload(secure_client, actors) -> dict:
    frame = make_classification_frame(150)
    dataset = secure_client.post(
        f"{API}/datasets",
        files={"file": ("d.csv", to_csv_bytes(frame))},
        headers=_bearer(actors["owner"]),
    )
    return {
        "name": "exp",
        "dataset_id": dataset.json()["dataset"]["id"],
        "target_column": "label",
        "problem_type": "classification",
        "algorithm": "random_forest",
    }


def _run_experiment(client, actors, payload) -> dict:
    headers = _bearer(actors["owner"])
    created = client.post(f"{API}/experiments", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    run = client.post(f"{API}/experiments/{created.json()['id']}/run", headers=headers)
    assert run.status_code == 200, run.text
    return run.json()


def test_experiment_models_accept_normal_prediction_input(
    secure_client, actors, owner_experiment_payload
) -> None:
    run = _run_experiment(secure_client, actors, owner_experiment_payload)
    assert run["status"] == "completed", run["error_message"]
    prediction = secure_client.post(
        f"{API}/models/{run['registered_model_id']}/predict",
        json={"records": [RECORD]},
        headers=_bearer(actors["owner"]),
    )
    assert prediction.status_code == 200, prediction.text
    assert prediction.json()["predictions"]


def test_experiment_without_validation_split_runs(
    secure_client, actors, owner_experiment_payload
) -> None:
    run = _run_experiment(
        secure_client, actors, {**owner_experiment_payload, "validation_size": 0.0}
    )
    assert run["status"] == "completed", run["error_message"]
    assert run["validation_metrics"] == {}


def test_experiment_failure_after_flush_error_is_recorded(
    secure_client, actors, owner_experiment_payload
) -> None:
    """A failed flush poisoned the session, so the run stayed 'running' and the API returned 500."""
    from sqlalchemy.exc import IntegrityError

    headers = _bearer(actors["owner"])
    created = secure_client.post(
        f"{API}/experiments", json=owner_experiment_payload, headers=headers
    )
    experiment_id = created.json()["id"]
    real_flush = Session.flush
    calls = {"n": 0}

    def failing_flush(self, *args, **kwargs):
        if any(type(obj).__name__ == "MLModel" for obj in self.new):
            calls["n"] += 1
            raise IntegrityError("INSERT", {}, Exception("duplicate version"))
        return real_flush(self, *args, **kwargs)

    with patch.object(Session, "flush", failing_flush):
        run = secure_client.post(f"{API}/experiments/{experiment_id}/run", headers=headers)
    assert calls["n"] >= 1
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "failed"
    detail = secure_client.get(f"{API}/experiments/{experiment_id}", headers=headers).json()
    assert detail["status"] == "failed"


def test_concurrent_run_of_same_experiment_is_refused(
    secure_client, actors, owner_experiment_payload, session_factory
) -> None:
    from datetime import UTC, datetime

    from app.database.models.experiment import ExperimentRun

    headers = _bearer(actors["owner"])
    created = secure_client.post(
        f"{API}/experiments", json=owner_experiment_payload, headers=headers
    )
    experiment_id = uuid.UUID(created.json()["id"])
    with session_factory() as session:
        session.get(Experiment, experiment_id).status = "running"
        session.add(
            ExperimentRun(
                experiment_id=experiment_id,
                run_number=1,
                status="running",
                started_at=datetime.now(UTC),
            )
        )
        session.commit()
    response = secure_client.post(f"{API}/experiments/{experiment_id}/run", headers=headers)
    assert response.status_code == 409


def test_orphaned_run_can_be_replaced(
    secure_client, actors, owner_experiment_payload, session_factory
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.database.models.experiment import ExperimentRun

    headers = _bearer(actors["owner"])
    created = secure_client.post(
        f"{API}/experiments", json=owner_experiment_payload, headers=headers
    )
    experiment_id = uuid.UUID(created.json()["id"])
    with session_factory() as session:
        session.get(Experiment, experiment_id).status = "running"
        session.add(
            ExperimentRun(
                experiment_id=experiment_id,
                run_number=1,
                status="running",
                started_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        session.commit()
    run = secure_client.post(f"{API}/experiments/{experiment_id}/run", headers=headers)
    assert run.status_code == 200, run.text
    assert run.json()["run_number"] == 2
    assert run.json()["status"] == "completed"
    with session_factory() as session:
        statuses = sorted(r.status for r in session.get(Experiment, experiment_id).runs)
    assert statuses == ["completed", "failed"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"test_size": 0.6, "validation_size": 0.5},
        {"hyperparameter_config": {"a": list(range(20)), "b": list(range(20))}},
    ],
)
def test_impossible_experiment_configs_are_rejected_up_front(overrides) -> None:
    base = {
        "name": "x",
        "dataset_id": uuid.uuid4(),
        "target_column": "t",
        "problem_type": "classification",
        "algorithm": "linear",
    }
    with pytest.raises(ValueError):
        ExperimentCreate(**base, **overrides)


# --- explainability ----------------------------------------------------------------------


def _xai_frame(kind: str) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 120
    frame = pd.DataFrame(
        {
            "a": rng.normal(size=n),
            "b": rng.integers(0, 5, n),
            "c": rng.choice(["x", "y", "z"], n),
        }
    )
    if kind == "binary":
        frame["t"] = np.where(frame.a + rng.normal(size=n) > 0, "yes", "no")
    elif kind == "multiclass":
        frame["t"] = rng.choice(["p", "q", "r"], n)
    else:
        frame["t"] = frame.a * 2 + rng.normal(size=n)
    return frame


XAI_RECORD = {"a": 0.5, "b": 2, "c": "y"}


@pytest.mark.parametrize(
    ("kind", "algorithm"),
    [
        ("binary", "linear"),
        ("binary", "random_forest"),
        ("multiclass", "random_forest"),
        ("regression", "linear"),
        ("regression", "random_forest"),
    ],
)
def test_explanations_work_for_mixed_type_features(
    secure_client, actors, kind, algorithm
) -> None:
    """Before the audit local SHAP/LIME returned 500 for every model with a categorical feature."""
    headers = _bearer(actors["owner"])
    dataset = secure_client.post(
        f"{API}/datasets",
        files={"file": ("d.csv", to_csv_bytes(_xai_frame(kind)))},
        headers=headers,
    )
    model = secure_client.post(
        f"{API}/models/train",
        json={
            "dataset_id": dataset.json()["dataset"]["id"],
            "target_column": "t",
            "algorithm": algorithm,
        },
        headers=headers,
    )
    assert model.status_code == 201, model.text
    base = f"{API}/models/{model.json()['id']}/explainability"

    shap = secure_client.post(f"{base}/shap", json={"record": XAI_RECORD}, headers=headers)
    assert shap.status_code == 200, shap.text
    body = shap.json()
    assert {c["feature"] for c in body["feature_contributions"]} == {"a", "b", "c"}
    assert next(c for c in body["feature_contributions"] if c["feature"] == "c")["value"] == "y"
    assert isinstance(body["base_value"], float)

    lime = secure_client.post(f"{base}/lime", json={"record": XAI_RECORD}, headers=headers)
    assert lime.status_code == 200, lime.text
    rules = lime.json()["rule_contributions"]
    assert rules
    assert all(rule["feature"] in {"a", "b", "c"} for rule in rules)

    global_view = secure_client.get(f"{base}/feature-importance", headers=headers)
    assert global_view.status_code == 200, global_view.text
    assert global_view.json()["method"] == "shap_kernel"
    assert {i["feature"] for i in global_view.json()["feature_importances"]} == {"a", "b", "c"}


def test_shap_contributions_explain_the_prediction(secure_client, actors) -> None:
    """Kernel SHAP's defining property: base value + contributions = the model's output."""
    headers = _bearer(actors["owner"])
    dataset = secure_client.post(
        f"{API}/datasets",
        files={"file": ("d.csv", to_csv_bytes(_xai_frame("regression")))},
        headers=headers,
    )
    model = secure_client.post(
        f"{API}/models/train",
        json={"dataset_id": dataset.json()["dataset"]["id"], "target_column": "t"},
        headers=headers,
    ).json()
    body = secure_client.post(
        f"{API}/models/{model['id']}/explainability/shap",
        json={"record": XAI_RECORD},
        headers=headers,
    ).json()
    total = body["base_value"] + sum(c["contribution"] for c in body["feature_contributions"])
    assert total == pytest.approx(body["prediction"], abs=0.01)


def test_target_class_selects_the_explained_class(secure_client, actors) -> None:
    headers = _bearer(actors["owner"])
    dataset = secure_client.post(
        f"{API}/datasets",
        files={"file": ("d.csv", to_csv_bytes(_xai_frame("multiclass")))},
        headers=headers,
    )
    model = secure_client.post(
        f"{API}/models/train",
        json={"dataset_id": dataset.json()["dataset"]["id"], "target_column": "t"},
        headers=headers,
    ).json()
    base = f"{API}/models/{model['id']}/explainability"
    for method in ("shap", "lime"):
        chosen = secure_client.post(
            f"{base}/{method}", json={"record": XAI_RECORD, "target_class": "r"}, headers=headers
        )
        assert chosen.status_code == 200, chosen.text
        assert chosen.json()["explained_class"] == "r"
        unknown = secure_client.post(
            f"{base}/{method}", json={"record": XAI_RECORD, "target_class": "?"}, headers=headers
        )
        assert unknown.status_code == 422


def test_estimator_importances_sum_one_hot_columns_per_feature() -> None:
    from app.ml.training import TrainingConfig, train_model

    frame = _xai_frame("binary")
    pipeline = train_model(frame, TrainingConfig(target_column="t", algorithm="random_forest")).pipeline
    scores = explainability_service._estimator_importances(pipeline, ["a", "b", "c"])
    assert sum(scores) == pytest.approx(1.0)
    assert all(score > 0 for score in scores)  # not the uniform fallback either
    assert len({round(s, 6) for s in scores}) == 3


# --- artifacts ---------------------------------------------------------------------------


def test_artifact_is_hashed_once_per_file_version(tmp_path) -> None:
    """Hashing per request cost 43-111 ms on a 25 MB forest; rewrites must still be caught."""
    import os

    import joblib

    from app.core.exceptions import ModelArtifactError
    from app.ml import persistence

    filename = f"{uuid.uuid4().hex}.joblib"
    path = tmp_path / filename
    joblib.dump({"format_version": persistence.ARTIFACT_FORMAT_VERSION, "pipeline": "x"}, path)
    digest = persistence.file_sha256(path)
    with patch.object(persistence, "file_sha256", wraps=persistence.file_sha256) as hashing:
        for _ in range(3):
            assert persistence.load_artifact(tmp_path, filename, digest)["pipeline"] == "x"
        assert hashing.call_count == 1

    # Same size, new timestamp: tampering is detected and nothing is unpickled.
    content = bytearray(path.read_bytes())
    content[-1] ^= 0xFF
    path.write_bytes(bytes(content))
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    with pytest.raises(ModelArtifactError):
        persistence.load_artifact(tmp_path, filename, digest)


# --- monitoring --------------------------------------------------------------------------


def test_ground_truth_length_must_match_the_prediction(secure_client, actors, owned) -> None:
    headers = _bearer(actors["owner"])
    secure_client.post(
        f"{API}/models/{owned['model']}/predict",
        json={"records": [RECORD]},
        headers=headers,
    )
    log = secure_client.get(
        f"{API}/models/{owned['model']}/predictions/history", headers=headers
    ).json()["items"][0]
    wrong = secure_client.post(
        f"{API}/predictions/history/{log['id']}/ground-truth",
        json={"ground_truth": ["a", "b"]},
        headers=headers,
    )
    assert wrong.status_code == 422
    right = secure_client.post(
        f"{API}/predictions/history/{log['id']}/ground-truth",
        json={"ground_truth": ["a"]},
        headers=headers,
    )
    assert right.status_code == 200


# --- restore script ----------------------------------------------------------------------


def _backup(tmp_path):
    import gzip
    import hashlib

    path = tmp_path / "b.sql.gz"
    with gzip.open(path, "wb") as handle:
        handle.write(b"SELECT 1;\n" * 10)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(f"{path.name}.sha256").write_text(f"{digest}  b.sql.gz\n", encoding="utf-8")
    return path


def test_restore_rejects_unsafe_database_names(tmp_path) -> None:
    with pytest.raises(ValueError):
        restore_db.restore_backup(_backup(tmp_path), 'x"; DROP DATABASE y; --', confirm=True)


def test_restore_stops_on_sql_errors_and_cannot_deadlock(tmp_path) -> None:
    proc = MagicMock()
    proc.wait.return_value = 0
    with (
        patch("subprocess.run", return_value=MagicMock(returncode=0)),
        patch("subprocess.Popen", return_value=proc) as popen,
    ):
        restore_db.restore_backup(_backup(tmp_path), "restore_test", confirm=True)
    args, kwargs = popen.call_args
    assert "ON_ERROR_STOP=1" in args[0]
    assert kwargs["stdout"] == subprocess.DEVNULL  # an unread stdout pipe blocks psql
    assert kwargs["stderr"] != subprocess.PIPE


def test_restore_reports_psql_failure(tmp_path) -> None:
    proc = MagicMock()
    proc.wait.return_value = 3
    with (
        patch("subprocess.run", return_value=MagicMock(returncode=0)),
        patch("subprocess.Popen", return_value=proc),
        pytest.raises(RuntimeError, match="code 3"),
    ):
        restore_db.restore_backup(_backup(tmp_path), "restore_test", confirm=True)
