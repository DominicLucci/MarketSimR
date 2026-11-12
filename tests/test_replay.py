"""The event log: ordering, ids and saving to disk."""

from marketsim.events import OrderAccepted, read_jsonl, to_record, write_jsonl
from marketsim.example import COMMANDS
from marketsim.script import Advance, Submit, run_script

from .helpers import BUY, SELL

SCRIPT = COMMANDS + [
    Submit(1, SELL, 1005, 2, expires_at=3),
    Submit(2, BUY, 990, 1),
    Submit(2, BUY, 0, 1),  # rejected
    Advance(3),  # expires the 1005 offer
]


def test_two_runs_of_the_same_script_are_identical():
    first, second = run_script(SCRIPT), run_script(SCRIPT)
    assert first.events == second.events
    assert first.accounts == second.accounts


def test_sequence_numbers_are_gapless_and_order_ids_are_acceptance_seqs():
    events = run_script(SCRIPT).events
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert all(e.order_id == e.seq for e in events if isinstance(e, OrderAccepted))
    assert all(a.time <= b.time for a, b in zip(events, events[1:]))


def test_log_survives_a_round_trip_through_a_file(tmp_path):
    events = run_script(SCRIPT).events
    path = tmp_path / "events.jsonl"
    write_jsonl(events, path)
    assert read_jsonl(path) == events
    assert {to_record(e)["type"] for e in events} >= {
        "AccountOpened",
        "OrderAccepted",
        "OrderRejected",
        "Trade",
        "OrderCancelled",
        "OrderExpired",
    }
