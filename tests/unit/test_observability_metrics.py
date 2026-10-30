import pytest
from starlette.testclient import TestClient

from app.main import app


def test_metrics_endpoint_returns_prometheus_format(api_client: TestClient) -> None:
    """Verify that GET /metrics returns 200 OK and valid Prometheus OpenMetrics text format."""
    response = api_client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")

    content = response.text
    # Check for expected Prometheus metrics families
    assert "# HELP aiml_models_total" in content
    assert "# TYPE aiml_models_total gauge" in content
    assert "aiml_models_total" in content

    assert "# HELP aiml_jobs_by_status" in content
    assert "# TYPE aiml_jobs_by_status gauge" in content
    assert 'aiml_jobs_by_status{status="completed"}' in content

    assert "# HELP aiml_predictions_total" in content
    assert "# TYPE aiml_predictions_total counter" in content

    assert "# HELP aiml_worker_health_status" in content
    assert "aiml_worker_health_status" in content
