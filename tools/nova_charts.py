"""Single offline Nova chart-data gateway. Never starts the trading application.

Usage: py -3 tools/nova_charts.py export --selection RESULT.json --sha256 SHA256 --output NEWDIR
The export command owns/cleans isolated children and returns PNG paths. No running desk needed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["serve", "export"])
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--port", type=int, default=8009)
    parser.add_argument("--frontend-origin", default="http://127.0.0.1:5179")
    parser.add_argument("--instance", default="manual-preview", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--samples", type=int, choices=range(51), default=0, metavar="0..50")
    args = parser.parse_args()
    if args.command == "export":
        if args.output is None:
            parser.error("export requires --output (a new directory)")
        from nova_chart_runner import export_charts
        import json
        print(json.dumps(export_charts(args.selection, args.sha256, args.output, args.samples)))
        return
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from agent_desk.chart_gallery import create_app
    import uvicorn
    app = create_app(args.selection, args.sha256, args.frontend_origin, args.instance)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
