"""Testes do AI Copilot: guardrails de SQL, degradação sem credencial e o loop
agêntico com o cliente Anthropic mockado (nenhuma chamada de rede real)."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.services.copilot import validate_sql

client = TestClient(app)


def _auth_headers():
    token = client.post(
        "/api/v1/auth/token", data={"username": "admin", "password": "adminpassword"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestSQLGuardrails:
    def test_accepts_select(self):
        assert validate_sql("SELECT * FROM fct_sales") == "SELECT * FROM fct_sales"

    def test_accepts_cte(self):
        sql = "WITH x AS (SELECT 1) SELECT * FROM x"
        assert validate_sql(sql) == sql

    def test_strips_trailing_semicolon(self):
        assert validate_sql("SELECT 1;") == "SELECT 1"

    @pytest.mark.parametrize(
        "sql",
        [
            "DELETE FROM fct_sales",
            "DROP TABLE dim_customers",
            "INSERT INTO fct_sales VALUES (1)",
            "UPDATE dim_customers SET status = 'x'",
            "CREATE TABLE hack AS SELECT 1",
            "ATTACH 'other.db'",
            "PRAGMA database_list",
        ],
    )
    def test_rejects_write_statements(self, sql):
        with pytest.raises(ValueError):
            validate_sql(sql)

    def test_rejects_multiple_statements(self):
        with pytest.raises(ValueError):
            validate_sql("SELECT 1; SELECT 2")

    def test_rejects_select_wrapping_forbidden_keyword(self):
        with pytest.raises(ValueError):
            validate_sql("SELECT * FROM fct_sales; DROP TABLE fct_sales")


class TestCopilotEndpoints:
    def test_chat_disabled_returns_503(self):
        with patch("app.config.COPILOT_ENABLED", False):
            resp = client.post(
                "/api/v1/copilot/chat", json={"message": "olá"}, headers=_auth_headers()
            )
        assert resp.status_code == 503
        assert "ANTHROPIC_API_KEY" in resp.json()["detail"]

    def test_chat_requires_auth(self):
        resp = client.post("/api/v1/copilot/chat", json={"message": "olá"})
        assert resp.status_code == 401

    def test_status_reports_disabled(self):
        with patch("app.config.COPILOT_ENABLED", False):
            resp = client.get("/api/v1/copilot/status", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json() == {"enabled": False, "model": None}


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(block_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=tool_input)


def _response(content, stop_reason):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
    )


class TestAgenticLoop:
    def test_tool_use_then_final_answer(self):
        from app.services import copilot

        responses = iter(
            [
                _response(
                    [_tool_use_block("tu_1", "query_analytics_dw", {"sql": "SELECT COUNT(*) AS n FROM fct_sales"})],
                    "tool_use",
                ),
                _response([_text_block("Existem 2392 vendas registradas.")], "end_turn"),
            ]
        )

        fake_client = SimpleNamespace(
            messages=SimpleNamespace(create=lambda **kwargs: next(responses))
        )

        with (
            patch.object(copilot, "get_client", return_value=fake_client),
            patch.object(copilot, "_run_sql_tool", return_value='{"columns": ["n"], "rows": [["2392"]], "row_count": 1}'),
        ):
            result = copilot.chat("quantas vendas temos?")

        assert result["answer"] == "Existem 2392 vendas registradas."
        assert len(result["tool_trace"]) == 1
        assert result["tool_trace"][0]["tool"] == "query_analytics_dw"
        assert result["tool_trace"][0]["is_error"] is False
        assert result["usage"]["input_tokens"] == 200

    def test_guardrail_error_is_reported_as_tool_error(self):
        from app.services import copilot

        responses = iter(
            [
                _response(
                    [_tool_use_block("tu_1", "query_analytics_dw", {"sql": "DROP TABLE fct_sales"})],
                    "tool_use",
                ),
                _response([_text_block("Não posso executar comandos de escrita.")], "end_turn"),
            ]
        )

        fake_client = SimpleNamespace(
            messages=SimpleNamespace(create=lambda **kwargs: next(responses))
        )

        with patch.object(copilot, "get_client", return_value=fake_client):
            result = copilot.chat("apague a tabela de vendas")

        assert result["tool_trace"][0]["is_error"] is True
        assert "guardrails" in result["tool_trace"][0]["result_preview"]

    def test_refusal_stop_reason(self):
        from app.services import copilot

        fake_client = SimpleNamespace(
            messages=SimpleNamespace(create=lambda **kwargs: _response([], "refusal"))
        )

        with patch.object(copilot, "get_client", return_value=fake_client):
            result = copilot.chat("pergunta bloqueada")

        assert "Não posso ajudar" in result["answer"]
