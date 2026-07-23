"""AI Copilot analítico: orquestração de LLM (Claude) com tool use sobre a plataforma.

O Copilot responde perguntas em linguagem natural sobre os dados combinando duas
ferramentas executadas no lado do servidor:

1. ``query_analytics_dw`` — text-to-SQL com guardrails: apenas ``SELECT``/``WITH``
   em uma conexão DuckDB read-only, um único statement, LIMIT imposto.
2. ``search_products_semantic`` — RAG sobre o catálogo de produtos usando a busca
   vetorial Qdrant + FastEmbed já existente na plataforma.

O loop agêntico é manual (request → tool_use → tool_result → ...) para manter o
controle de auditoria: cada chamada de ferramenta é registrada em um trace que a
UI exibe ao usuário (transparência sobre qual SQL foi executado).
"""
import json
import logging
import os
import re

import anthropic
import duckdb

from domains.common.paths import get_db_path

from .. import config

logger = logging.getLogger("AI_Copilot")

# Tabelas expostas ao modelo — espelha os marts do dbt (mantido em sincronia manualmente)
_SCHEMA_DOC = """
Tabelas disponíveis no Data Warehouse (DuckDB):

- dim_customers(customer_id INT PK, customer_name TEXT, email TEXT, created_at TIMESTAMP, status TEXT['active'|'inactive'], is_active_flag INT)
- fct_sales(sale_id INT PK, customer_id INT FK, customer_name TEXT, product_name TEXT, amount DOUBLE, competitor_price DOUBLE, status TEXT['COMPLETED'|'PENDING'|'CANCELLED'], sale_date TIMESTAMP, is_orphan_join INT)
- dim_products(product_id INT PK, product_name TEXT, description TEXT, category TEXT)
- dm_monthly_kpis(sales_month DATE, net_revenue DOUBLE, completed_orders_count BIGINT, average_ticket DOUBLE, unique_customers BIGINT)
- dm_customer_ltv(customer_id INT PK, customer_name TEXT, total_orders BIGINT, lifetime_value DOUBLE, avg_ticket DOUBLE, first_purchase_at TIMESTAMP, last_purchase_at TIMESTAMP, recency_days INT, recency_score INT, frequency_score INT, monetary_score INT, rfm_segment TEXT)
- ml_features_pricing(product_name TEXT, sale_date DATE, price DOUBLE, competitor_price DOUBLE, units_sold BIGINT, total_revenue DOUBLE, day_of_week INT, is_weekend INT)
"""

SYSTEM_PROMPT = f"""Você é o AI Copilot da plataforma Enterprise Data Mesh & Lakehouse — um assistente \
analítico para perguntas sobre vendas, clientes, produtos e KPIs.

{_SCHEMA_DOC}

Regras:
- Para perguntas quantitativas, gere SQL (dialeto DuckDB) e execute via query_analytics_dw. \
Apenas SELECT/WITH; a conexão é read-only e resultados são truncados em {config.COPILOT_SQL_ROW_LIMIT} linhas.
- Para perguntas sobre o catálogo de produtos por características ("fone com cancelamento de ruído"), \
use search_products_semantic.
- Responda em português, de forma direta: primeiro a resposta, depois 1-2 frases de contexto. \
Formate valores monetários como R$ 1.234,56.
- Se a pergunta não puder ser respondida com os dados disponíveis, diga isso claramente em vez de inventar.
"""

TOOLS = [
    {
        "name": "query_analytics_dw",
        "description": (
            "Executa uma consulta SQL somente-leitura (SELECT/WITH, dialeto DuckDB) no Data Warehouse "
            "analítico. Use para qualquer pergunta quantitativa sobre vendas, clientes, KPIs, LTV ou "
            "features de pricing. Um único statement por chamada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A consulta SQL (apenas SELECT ou WITH)."}
            },
            "required": ["sql"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "search_products_semantic",
        "description": (
            "Busca semântica no catálogo de produtos (banco vetorial Qdrant + embeddings). Use quando o "
            "usuário descrever um produto por características em linguagem natural, sem nome exato."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Descrição em linguagem natural do produto."}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|export|install|load|pragma|set|call|grant|vacuum)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str) -> str:
    """Valida a consulta gerada pelo modelo antes de executá-la (defesa em profundidade —
    a conexão já é read-only). Retorna o SQL normalizado ou levanta ValueError."""
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        raise ValueError("Apenas um statement SQL por chamada é permitido.")
    first_word = cleaned.split(None, 1)[0].lower() if cleaned else ""
    if first_word not in ("select", "with"):
        raise ValueError("Apenas consultas SELECT/WITH são permitidas.")
    if _FORBIDDEN_SQL.search(cleaned):
        raise ValueError("A consulta contém comandos não permitidos (somente leitura).")
    return cleaned


def _run_sql_tool(sql: str) -> str:
    cleaned = validate_sql(sql)
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return json.dumps({"error": "Data Warehouse ainda não materializado. Execute a pipeline no Airflow."})

    conn = duckdb.connect(db_path, read_only=True)
    try:
        cursor = conn.execute(f"SELECT * FROM ({cleaned}) LIMIT {config.COPILOT_SQL_ROW_LIMIT}")
        columns = [d[0] for d in cursor.description]
        rows = [[str(v) if v is not None else None for v in row] for row in cursor.fetchall()]
    finally:
        conn.close()

    return json.dumps({"columns": columns, "rows": rows, "row_count": len(rows)}, ensure_ascii=False)


def _run_semantic_search_tool(query: str) -> str:
    # Import tardio para não pagar o custo do modelo de embeddings quando o Copilot não é usado
    from ..deps import get_embedding_model, qdrant_client

    model = get_embedding_model()
    query_vector = list(model.embed([query]))[0].tolist()
    hits = qdrant_client.search(collection_name="products", query_vector=query_vector, limit=5)
    results = [
        {
            "name": h.payload.get("name"),
            "category": h.payload.get("category"),
            "description": h.payload.get("description"),
            "similarity_score": round(h.score, 4),
        }
        for h in hits
    ]
    return json.dumps({"results": results}, ensure_ascii=False)


def _execute_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Executa uma ferramenta e retorna (conteúdo, is_error)."""
    try:
        if name == "query_analytics_dw":
            return _run_sql_tool(tool_input["sql"]), False
        if name == "search_products_semantic":
            return _run_semantic_search_tool(tool_input["query"]), False
        return f"Ferramenta desconhecida: {name}", True
    except ValueError as e:
        return f"Consulta rejeitada pelos guardrails: {e}", True
    except Exception as e:
        logger.error(f"Erro ao executar ferramenta {name}: {e}")
        return f"Erro ao executar a ferramenta: {e}", True


_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def chat(message: str, history: list[dict] | None = None) -> dict:
    """Executa um turno completo do Copilot (loop agêntico com tool use).

    ``history`` é uma lista de {"role": "user"|"assistant", "content": str} dos
    turnos anteriores — apenas texto, para manter o payload enxuto.
    """
    client = get_client()

    messages: list[dict] = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in (history or [])
        if turn.get("role") in ("user", "assistant") and turn.get("content")
    ]
    messages.append({"role": "user", "content": message})

    tool_trace: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0

    for _ in range(config.COPILOT_MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=config.COPILOT_MODEL,
            max_tokens=config.COPILOT_MAX_TOKENS,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            thinking={"type": "adaptive"},
            tools=TOOLS,
            messages=messages,
        )
        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        if response.stop_reason == "refusal":
            return {
                "answer": "Não posso ajudar com essa solicitação.",
                "tool_trace": tool_trace,
                "usage": {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens},
            }

        if response.stop_reason != "tool_use":
            answer = "".join(b.text for b in response.content if b.type == "text")
            return {
                "answer": answer,
                "tool_trace": tool_trace,
                "usage": {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens},
            }

        # Preserva o conteúdo integral (incluindo blocos de thinking) no histórico do loop
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            content, is_error = _execute_tool(block.name, block.input)
            tool_trace.append(
                {
                    "tool": block.name,
                    "input": block.input,
                    "is_error": is_error,
                    "result_preview": content[:500],
                }
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return {
        "answer": "Atingi o limite de etapas de ferramenta sem concluir. Tente uma pergunta mais específica.",
        "tool_trace": tool_trace,
        "usage": {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens},
    }
