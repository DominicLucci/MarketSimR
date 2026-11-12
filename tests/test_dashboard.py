"""The dashboard shows the same market as the batch runner, and its export is enough to
recover the settings."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from marketsim.config import SimConfig
from marketsim.dashboard import config_from_query, make_server, run_payload
from marketsim.metrics import summarize
from marketsim.simulation import run_simulation

CONFIG = SimConfig(seed=3, informed_share=0.5, n_steps=300)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # talk to localhost directly


def test_payload_agrees_with_the_batch_runner():
    payload, batch = run_payload(CONFIG), run_simulation(CONFIG)
    assert payload["summary"] == summarize(batch)
    assert len(payload["trades"]) == payload["summary"]["n_trades"]
    assert sum(t[2] for t in payload["trades"]) == payload["summary"]["volume"]
    assert len(payload["value"]) == CONFIG.n_steps
    assert payload["value"][0] == CONFIG.initial_value


def test_settings_can_be_recovered_from_an_export():
    exported = json.loads(json.dumps({"runs": [run_payload(CONFIG)]}))  # what the download holds
    manifest = exported["runs"][0]["manifest"]
    recovered = SimConfig.from_dict(manifest["config"])
    assert recovered == CONFIG
    assert summarize(run_simulation(recovered)) == exported["runs"][0]["summary"]


def test_query_validation():
    assert config_from_query({"seed": ["4"], "informed_share": ["0.1"]}) == SimConfig(seed=4, informed_share=0.1)
    for bad in ({"seed": ["-1"]}, {"n_steps": ["0"]}, {"n_steps": ["999999"]}, {"informed_share": ["0.33"]}, {"seed": ["x"]}):
        with pytest.raises(ValueError):
            config_from_query(bad)


@pytest.fixture()
def base_url():
    server = make_server(port=0)  # any free port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_server_serves_the_page_and_the_same_run(base_url):
    page = OPENER.open(base_url + "/").read().decode()
    assert "<title>MarketSim</title>" in page and "/api/run" in page

    options = json.load(OPENER.open(base_url + "/api/options"))
    assert options["shares"] == [0.0, 0.1, 0.25, 0.5, 0.75]

    served = json.load(OPENER.open(base_url + "/api/run?seed=3&informed_share=0.5&n_steps=300"))
    assert served == json.loads(json.dumps(run_payload(CONFIG)))


def test_server_rejects_bad_requests(base_url):
    with pytest.raises(urllib.error.HTTPError) as bad_share:
        OPENER.open(base_url + "/api/run?seed=1&informed_share=0.33")
    assert bad_share.value.code == 400 and "whole number of traders" in json.load(bad_share.value)["error"]
    with pytest.raises(urllib.error.HTTPError) as missing:
        OPENER.open(base_url + "/nothing")
    assert missing.value.code == 404
