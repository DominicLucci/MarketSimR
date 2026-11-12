"""A saved run can be regenerated from its manifest alone, and the command line works."""

import json

from marketsim.config import SimConfig
from marketsim.events import read_jsonl
from marketsim.metrics import summarize
from marketsim.run import main, trace_text
from marketsim.simulation import run_simulation
from marketsim.storage import save_run


def test_saved_manifest_is_enough_to_regenerate_the_run(tmp_path):
    original = run_simulation(SimConfig(seed=3, n_steps=400, informed_share=0.5))
    out = save_run(original, tmp_path / "run")
    assert {p.name for p in out.iterdir()} == {
        "manifest.json",
        "summary.json",
        "events.jsonl",
        "decisions.csv",
        "traders.csv",
        "value_path.csv",
        "quotes.csv",
    }
    manifest = json.loads((out / "manifest.json").read_text())
    again = run_simulation(SimConfig.from_dict(manifest["config"]))
    assert manifest["model_version"] == again.model_version
    assert read_jsonl(out / "events.jsonl") == again.events
    assert json.loads((out / "summary.json").read_text()) == summarize(again)


def test_command_line_run_and_trace(capsys):
    result = main(["--seed", "2", "--informed-share", "0.5", "--steps", "300", "--trace-step", "10"])
    printed = capsys.readouterr().out
    assert "informed share 50% (20 of 40 traders)" in printed
    assert "step 10: trader" in printed and "hidden from the trader" in printed
    assert result.config.seed == 2
    for step in range(300):  # every arrival can be explained without error
        assert trace_text(result, step).startswith(f"step {step}:")
