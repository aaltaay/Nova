"""Nova API composition root: environment, lifespan, middleware, and routes."""
from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI

from logging_setup import configure_logging
from paths import env_file_path

configure_logging()
load_dotenv(env_file_path())

from app_lifespan import configure_cors, lifespan  # noqa: E402
from app_routers import register_routers  # noqa: E402
from auth import configure_api_auth  # noqa: E402

from api_instance_lock import acquire_or_exit  # noqa: E402

app = FastAPI(
    title="Nova API",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "bot",
            "description": (
                "Localhost brain-agnostic bot API (ADR 016). Loopback only. "
                "Advise never places. Orders go through execution.service "
                "with source=bot. L3 Unrestricted is parked (#216)."
            ),
        },
        {
            "name": "bot-ws",
            "description": "Bot Eyes quotes + append-only audit WebSockets (loopback).",
        },
    ],
)
register_routers(app)
configure_api_auth(app)
configure_cors(app)
acquire_or_exit()
