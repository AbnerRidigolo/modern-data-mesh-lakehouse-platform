"""Testes do pipeline de streaming de marketing (Redpanda / Kafka).

Focam na lógica pura (validação de contrato, particionamento válido/inválido e
roteamento para a DLQ), sem exigir um broker Kafka rodando. A escrita no Delta
Lake é isolada por monkeypatch.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domains.streaming import consumer as stream_consumer  # noqa: E402
from domains.streaming.producer import generate_event  # noqa: E402


def _valid_event():
    return {
        "event_id": 900001,
        "campaign": "Setup Gamer",
        "channel": "Google Ads",
        "category": "Periféricos",
        "spend": 120.50,
        "impressions": 5000,
        "clicks": 250,
        "event_date": "2026-07-01T12:00:00+00:00",
    }


def test_generate_event_respects_contract_invariants():
    for _ in range(200):
        ev = generate_event()
        assert ev["spend"] > 0
        assert ev["clicks"] <= ev["impressions"]
        assert ev["channel"] in {"Google Ads", "Meta Ads", "Email", "Influencer"}


def test_generate_invalid_event_breaks_clicks_invariant():
    ev = generate_event(inject_invalid=True)
    assert ev["clicks"] > ev["impressions"]


def test_validate_record_accepts_valid_event():
    validated, error = stream_consumer.validate_record(_valid_event())
    assert error is None
    assert validated is not None
    assert validated["event_id"] == 900001


def test_validate_record_rejects_clicks_gt_impressions():
    bad = _valid_event()
    bad["clicks"] = bad["impressions"] + 10
    validated, error = stream_consumer.validate_record(bad)
    assert validated is None
    assert error is not None


def test_validate_record_rejects_invalid_channel():
    bad = _valid_event()
    bad["channel"] = "TikTok Ads"
    validated, error = stream_consumer.validate_record(bad)
    assert validated is None


def test_partition_batch_splits_valid_and_invalid():
    bad = _valid_event()
    bad["event_id"] = 900002
    bad["spend"] = -5.0  # viola spend > 0
    result = stream_consumer.partition_batch([_valid_event(), bad])
    assert len(result.valid) == 1
    assert len(result.invalid) == 1
    assert result.valid[0]["event_id"] == 900001
    # invalid guarda o registro cru + a mensagem de erro
    raw, error = result.invalid[0]
    assert raw["event_id"] == 900002
    assert error


def test_flush_to_delta_noop_on_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(stream_consumer, "write_deltalake", lambda *a, **k: calls.append(1))
    written = stream_consumer.flush_to_delta([])
    assert written == 0
    assert not calls


def test_flush_to_delta_writes_valid_records(monkeypatch, tmp_path):
    captured = {}

    def fake_write(path, table, mode=None, storage_options=None):
        captured["path"] = path
        captured["rows"] = table.num_rows
        captured["mode"] = mode

    monkeypatch.setattr(stream_consumer, "write_deltalake", fake_write)
    monkeypatch.setattr(stream_consumer, "s3_enabled", lambda: False)
    monkeypatch.setattr(stream_consumer, "get_delta_table_path", lambda key: str(tmp_path / "campaigns"))

    validated, _ = stream_consumer.validate_record(_valid_event())
    written = stream_consumer.flush_to_delta([validated])

    assert written == 1
    assert captured["rows"] == 1
    assert captured["mode"] == "append"


class _FakeProducer:
    """Producer fake que grava as mensagens enviadas (para verificar a DLQ)."""

    def __init__(self):
        self.sent = []

    def send(self, topic, value=None, key=None):
        self.sent.append((topic, value))

    def flush(self):
        pass


def test_send_to_dlq_publishes_invalid_events():
    fake = _FakeProducer()
    proc = stream_consumer.StreamProcessor(producer=fake)
    bad = _valid_event()
    proc._send_to_dlq([(bad, "erro de contrato")])
    assert len(fake.sent) == 1
    topic, payload = fake.sent[0]
    assert topic == stream_consumer.config.TOPIC_MARKETING_DLQ
    assert payload["record"]["event_id"] == 900001
    assert payload["error"] == "erro de contrato"
