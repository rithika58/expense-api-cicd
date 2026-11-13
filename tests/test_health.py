"""Health and version endpoints - the contract the pipeline depends on."""


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"] == "test-sha"


def test_health_sets_request_id_header(client):
    response = client.get("/health")
    assert response.headers["X-Request-ID"]


def test_request_id_is_propagated(client):
    response = client.get("/health", headers={"X-Request-ID": "abc12345"})
    assert response.headers["X-Request-ID"] == "abc12345"


def test_version_endpoint(client):
    response = client.get("/version")
    assert response.status_code == 200
    assert response.get_json()["git_sha"] == "test-sha"


def test_unknown_route_returns_json_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


def test_method_not_allowed(client):
    response = client.put("/health")
    assert response.status_code == 405
    assert response.get_json()["error"] == "method_not_allowed"
