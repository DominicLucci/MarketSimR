"""A small local dashboard with no dependencies beyond the simulator's own.

    python -m marketsim.dashboard            # then open http://127.0.0.1:8000
    python -m marketsim.dashboard --port 8050

The page asks this server for a run and the server calls `run_simulation`, the same
function the command line and the experiment use. So the dashboard cannot show a different
market from the batch runner for the same settings; `tests/test_dashboard.py` checks that.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import SimConfig
from .events import Side, Trade
from .experiment import SHARES
from .metrics import summarize, trader_outcomes
from .simulation import run_simulation
from .storage import run_manifest

PAGE = Path(__file__).with_name("dashboard.html")
MAX_STEPS = 20_000


def run_payload(config: SimConfig) -> dict[str, Any]:
    """Everything the page shows for one run, and everything the export contains."""
    result = run_simulation(config)
    trades = [
        [e.time, e.price, e.quantity, int(e.buyer_id in result.informed), int(e.seller_id in result.informed), int(e.aggressor is Side.BUY)]
        for e in result.events
        if isinstance(e, Trade)
    ]
    return {
        "manifest": run_manifest(result),
        "summary": summarize(result),
        "columns": {
            "value": "underlying value in ticks, one entry per step",
            "trades": ["step", "price_ticks", "quantity", "buyer_better_informed", "seller_better_informed", "incoming_order_was_buy"],
            "quotes": ["step", "best_bid_ticks", "bid_size", "best_ask_ticks", "ask_size"],
        },
        "value": [round(float(v), 2) for v in result.value_path],
        "trades": trades,
        "quotes": [list(sample) for sample in result.quote_samples],
        "traders": trader_outcomes(result),
    }


def config_from_query(query: dict[str, list[str]]) -> SimConfig:
    """Only the seed, the informed share and the run length can be set from the page."""
    defaults = SimConfig()
    seed = int(query.get("seed", ["0"])[0])
    share = float(query.get("informed_share", [str(defaults.informed_share)])[0])
    steps = int(query.get("n_steps", [str(defaults.n_steps)])[0])
    if seed < 0 or not 1 <= steps <= MAX_STEPS:
        raise ValueError(f"seed must be 0 or more and n_steps between 1 and {MAX_STEPS}")
    return SimConfig(seed=seed, informed_share=share, n_steps=steps)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, "application/json", json.dumps(data).encode())

    def do_GET(self) -> None:  # noqa: N802 (name fixed by http.server)
        url = urlparse(self.path)
        if url.path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE.read_bytes())
        elif url.path == "/favicon.ico":
            self._send(204, "image/x-icon", b"")
        elif url.path == "/api/options":
            defaults = SimConfig()
            self._json(200, {"shares": list(SHARES), "defaults": defaults.to_dict(), "max_steps": MAX_STEPS})
        elif url.path == "/api/run":
            try:
                config = config_from_query(parse_qs(url.query))
            except (ValueError, TypeError) as error:
                self._json(400, {"error": str(error)})
                return
            self._json(200, run_payload(config))
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, format: str, *args: Any) -> None:  # keep the terminal quiet
        pass


def make_server(port: int = 8000, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the MarketSim dashboard on this computer.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    server = make_server(args.port)
    print(f"MarketSim dashboard: http://127.0.0.1:{args.port}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
