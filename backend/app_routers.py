"""Register FastAPI routers on the app factory.

Keeps ``main.py`` under the file-size limit — add new routers here, not in main.
"""
from __future__ import annotations

from fastapi import FastAPI

from routes.trading import router as trading_router, ws_router as trading_ws_router
from routes.strategy import router as strategy_router
from routes.journal import router as journal_router
from routes.executor import router as executor_router
from routes.l2 import router as l2_router
from routes.news import router as news_router
from routes.ticker import router as ticker_router
from routes.chart_drawings import router as chart_drawings_router
from scanner_push import router as scanner_ws_router
from routes.health import router as health_router
from routes.scan import router as scan_router
from routes.hod_momo import router as hod_momo_router, ws_router as hod_momo_ws_router
from routes.client_errors import router as client_errors_router
from routes.nova_os import router as nova_os_router
from routes.archive import router as archive_router
from routes.backtest import router as backtest_router
from routes.alerts import router as alerts_router
from routes.metrics import router as metrics_router
from routes.earnings import router as earnings_router
from routes.volume_boost import router as volume_boost_router
from routes.advise import router as advise_router, ws_router as advise_ws_router
from routes.halts import router as halts_router
from routes.bot import router as bot_router
from routes.bot_ws import ws_router as bot_ws_router
from sim.routes import router as sim_router
from sensors.routes import router as sensors_router


def register_routers(app: FastAPI) -> None:
    app.include_router(trading_router)
    app.include_router(trading_ws_router)
    app.include_router(scanner_ws_router)
    app.include_router(strategy_router)
    app.include_router(journal_router)
    app.include_router(executor_router)
    app.include_router(l2_router)
    app.include_router(news_router)
    app.include_router(ticker_router)
    app.include_router(chart_drawings_router)
    app.include_router(health_router)
    app.include_router(scan_router)
    app.include_router(hod_momo_router)
    app.include_router(hod_momo_ws_router)
    app.include_router(client_errors_router)
    app.include_router(nova_os_router)
    app.include_router(archive_router)
    app.include_router(backtest_router)
    app.include_router(alerts_router)
    app.include_router(metrics_router)
    app.include_router(earnings_router)
    app.include_router(volume_boost_router)
    app.include_router(advise_router)
    app.include_router(advise_ws_router)
    app.include_router(halts_router)
    app.include_router(bot_router)
    app.include_router(bot_ws_router)
    app.include_router(sim_router)
    app.include_router(sensors_router)
