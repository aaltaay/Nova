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

app = FastAPI(title="Nova API", lifespan=lifespan)
register_routers(app)
configure_api_auth(app)
configure_cors(app)
