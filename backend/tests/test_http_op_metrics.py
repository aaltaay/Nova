"""HTTP operation timing uses route templates and honest failures."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app_lifespan import configure_cors
from metrics import op_metrics
from metrics.http_middleware import HttpOperationMetricsMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(HttpOperationMetricsMiddleware)

    @app.get("/api/ticker/{symbol}")
    async def ticker(symbol: str):
        return {"symbol": symbol}

    @app.get("/api/rejected")
    async def rejected():
        raise HTTPException(status_code=503, detail="expected")

    @app.get("/api/crash")
    async def crash():
        raise RuntimeError("expected")

    return app


def setup_function() -> None:
    op_metrics.reset_for_tests()


def teardown_function() -> None:
    op_metrics.reset_for_tests()


def test_route_template_coalesces_dynamic_paths() -> None:
    client = TestClient(_app())
    assert client.get("/api/ticker/AAPL").status_code == 200
    assert client.get("/api/ticker/MSFT").status_code == 200

    operations = op_metrics.snapshot()["operations"]
    assert operations["http.GET./api/ticker/{symbol}"]["count"] == 2
    assert not any("AAPL" in name or "MSFT" in name for name in operations)


def test_status_and_exception_paths_count_as_errors() -> None:
    client = TestClient(_app(), raise_server_exceptions=False)
    assert client.get("/api/rejected").status_code == 503
    assert client.get("/api/crash").status_code == 500
    assert client.get("/does/not/exist").status_code == 404

    operations = op_metrics.snapshot()["operations"]
    assert operations["http.GET./api/rejected"]["error_count"] == 1
    assert operations["http.GET./api/crash"]["error_count"] == 1
    assert operations["http.GET.unmatched"]["error_count"] == 1


def test_app_lifespan_wires_metrics_middleware() -> None:
    app = FastAPI()
    configure_cors(app)

    middleware_classes = [entry.cls for entry in app.user_middleware]
    assert HttpOperationMetricsMiddleware in middleware_classes
