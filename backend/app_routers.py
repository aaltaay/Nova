"""Register FastAPI routers on the app factory.

Keeps ``main.py`` under the file-size limit — add new routers here, not in main.
"""
from __future__ import annotations

from fastapi import FastAPI

from routes.trading import router as trading_router, ws_router as trading_ws_router
from routes.strategy import router as strategy_router
from routes.journal import router as journal_router
from routes.kill_switch import router as kill_switch_router
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
from routes.symbols import router as symbols_router
from routes.bot import router as bot_router
from routes.bot_ws import ws_router as bot_ws_router
from sim.routes import router as sim_router
from capture.routes import router as capture_router
from sensors.focus_routes import router as focus_router
from sensors.routes import router as sensors_router
from practice.routes import router as practice_router
from routes.desk import router as desk_router
from diagnostics.routes import router as diagnostics_router
from leaderboard.routes import router as leaderboard_router
from setup_scanner.routes import router as setups_router
from setup_templates.routes import install as install_setup_template_refusals
from setup_templates.routes import router as setup_templates_router
from eyes.routes import router as eyes_router
from perf.routes import router as perf_router
from catalysts.routes import router as catalysts_router
from move_reason.routes import router as move_reason_router
from issue_report.routes import router as issue_report_router
from stock_read.routes import router as stock_read_router


def register_routers(app: FastAPI) -> None:
    app.include_router(trading_router)
    app.include_router(trading_ws_router)
    app.include_router(scanner_ws_router)
    app.include_router(strategy_router)
    app.include_router(journal_router)
    app.include_router(kill_switch_router)
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
    app.include_router(symbols_router)
    app.include_router(bot_router)
    app.include_router(bot_ws_router)
    app.include_router(sim_router)
    app.include_router(capture_router)
    app.include_router(sensors_router)
    app.include_router(focus_router)
    app.include_router(practice_router)
    app.include_router(desk_router)
    app.include_router(diagnostics_router)
    app.include_router(leaderboard_router)
    app.include_router(setups_router)
    app.include_router(setup_templates_router)
    install_setup_template_refusals(app)
    app.include_router(eyes_router)
    app.include_router(perf_router)
    app.include_router(catalysts_router)
    app.include_router(move_reason_router)
    app.include_router(issue_report_router)
    app.include_router(stock_read_router)
