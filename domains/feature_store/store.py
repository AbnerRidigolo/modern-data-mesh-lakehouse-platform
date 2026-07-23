"""Feature Store leve sobre a stack existente (DuckDB offline + Redis online).

Implementa os quatro conceitos centrais de um feature store de produção sem o
peso de um framework dedicado:

1. **Registry declarativo** (``registry.yml``): entidades, feature views, TTL,
   owners — governança versionada no git.
2. **Offline store** (DuckDB / feature views do dbt): fonte histórica para
   treino, consultada via **point-in-time join** (ASOF) — para cada evento no
   spine, pega-se a última linha de feature com ``timestamp <= event_ts``,
   nunca do futuro. É a correção que evita data leakage.
3. **Online store** (Redis, com fallback em memória): o snapshot mais recente
   por entidade, servido em baixa latência com TTL. Materializado pelo Airflow.
4. **Freshness / lineage**: cada view reporta a idade do dado servido.

A engine é usada tanto pela API (serving) quanto por scripts de treino e pela
task de materialização no Airflow.
"""
import json
import logging
import os
from datetime import UTC, datetime

import duckdb
import pandas as pd
import yaml

from domains.common.paths import get_db_path

logger = logging.getLogger("FeatureStore")

_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "registry.yml")
_ONLINE_KEY_PREFIX = "fs"


def load_registry(path: str = _REGISTRY_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class FeatureStore:
    def __init__(self, registry_path: str = _REGISTRY_PATH, redis_client=None, db_path: str | None = None):
        self.registry = load_registry(registry_path)
        self.db_path = db_path or get_db_path()
        self._redis = redis_client
        self._online_fallback: dict[str, str] = {}  # usado quando o Redis está indisponível

    # ------------------------------------------------------------------ helpers

    def _view(self, view_name: str) -> dict:
        views = self.registry["feature_views"]
        if view_name not in views:
            raise KeyError(f"Feature view '{view_name}' não existe no registry.")
        return views[view_name]

    def _feature_names(self, view: dict) -> list[str]:
        return [f["name"] for f in view["features"]]

    def _connect(self) -> duckdb.DuckDBPyConnection:
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"DuckDB não encontrado em {self.db_path}. Execute a pipeline dbt primeiro.")
        return duckdb.connect(self.db_path, read_only=True)

    def _online_key(self, view_name: str, entity_id) -> str:
        return f"{_ONLINE_KEY_PREFIX}:{view_name}:{entity_id}"

    # ------------------------------------------------------------- offline (PIT)

    def get_historical_features(
        self, view_name: str, entity_df: pd.DataFrame, event_timestamp_col: str = "event_timestamp"
    ) -> pd.DataFrame:
        """Point-in-time join: enriquece ``entity_df`` (spine com a chave de entidade
        + timestamp do evento) com as features vigentes AO EVENTO, via ASOF JOIN.

        Garante que uma amostra de treino nunca recebe features computadas depois
        do seu próprio timestamp — a causa nº 1 de vazamento em pipelines de ML.
        """
        view = self._view(view_name)
        entity = self.registry["entities"][view["entity"]]
        join_key = entity["join_key"]
        ts_field = view["timestamp_field"]
        features = self._feature_names(view)

        if join_key not in entity_df.columns or event_timestamp_col not in entity_df.columns:
            raise ValueError(f"entity_df precisa das colunas '{join_key}' e '{event_timestamp_col}'.")

        spine = entity_df[[join_key, event_timestamp_col]].copy()
        spine[event_timestamp_col] = pd.to_datetime(spine[event_timestamp_col])

        conn = self._connect()
        try:
            conn.register("spine", spine)
            feature_cols = ", ".join(f"fv.{c}" for c in features)
            # ASOF JOIN: para cada linha do spine, casa a última linha da feature
            # view com timestamp <= o timestamp do evento (inequality join nativo).
            query = f"""
                SELECT s.{join_key},
                       s.{event_timestamp_col},
                       {feature_cols}
                FROM spine s
                ASOF LEFT JOIN {view['source_table']} fv
                  ON s.{join_key} = fv.{join_key}
                 AND s.{event_timestamp_col} >= fv.{ts_field}
                ORDER BY s.{event_timestamp_col}
            """
            result = conn.execute(query).fetchdf()
        finally:
            conn.close()
        return result

    # -------------------------------------------------------------- online store

    def _redis_available(self) -> bool:
        if self._redis is None:
            return False
        try:
            self._redis.ping()
            return True
        except Exception:
            return False

    def materialize(self, view_name: str | None = None) -> dict:
        """Materializa o snapshot mais recente por entidade do offline store para o
        online store (Redis). Chamado pela task de materialização no Airflow."""
        views = [view_name] if view_name else list(self.registry["feature_views"].keys())
        report = {}
        use_redis = self._redis_available()

        conn = self._connect()
        try:
            for name in views:
                view = self._view(name)
                entity = self.registry["entities"][view["entity"]]
                join_key = entity["join_key"]
                ts_field = view["timestamp_field"]
                features = self._feature_names(view)
                ttl = int(view["online_ttl_seconds"])

                cols = ", ".join([join_key, ts_field, *features])
                # Última linha por entidade (o snapshot que o online store deve servir)
                latest = conn.execute(
                    f"""
                    SELECT {cols} FROM (
                        SELECT {cols},
                               ROW_NUMBER() OVER (PARTITION BY {join_key} ORDER BY {ts_field} DESC) AS rn
                        FROM {view['source_table']}
                    ) WHERE rn = 1
                    """
                ).fetchdf()

                written = 0
                for row in latest.to_dict(orient="records"):
                    entity_id = row[join_key]
                    payload = {
                        "features": {c: _jsonable(row[c]) for c in features},
                        "event_timestamp": _jsonable(row[ts_field]),
                        "materialized_at": datetime.now(UTC).isoformat(),
                    }
                    key = self._online_key(name, entity_id)
                    serialized = json.dumps(payload, ensure_ascii=False)
                    if use_redis:
                        self._redis.setex(key, ttl, serialized)
                    else:
                        self._online_fallback[key] = serialized
                    written += 1
                report[name] = {"entities_written": written, "backend": "redis" if use_redis else "in_memory"}
                logger.info(f"Materializado '{name}': {written} entidades ({report[name]['backend']}).")
        finally:
            conn.close()
        return report

    def get_online_features(self, view_name: str, entity_id) -> dict:
        """Lê o vetor de features de uma entidade do online store (baixa latência).

        Em cache miss (nunca materializado ou TTL expirado), faz fallback para o
        snapshot mais recente do offline store — o serving nunca fica sem resposta.
        """
        view = self._view(view_name)
        key = self._online_key(view_name, entity_id)

        raw = None
        source = "online_redis"
        if self._redis_available():
            try:
                raw = self._redis.get(key)
            except Exception:
                raw = None
        if raw is None and key in self._online_fallback:
            raw, source = self._online_fallback[key], "online_memory"

        if raw is not None:
            payload = json.loads(raw)
            payload["source"] = source
            payload["entity_id"] = _jsonable(entity_id)
            return payload

        # Fallback offline: consulta a linha mais recente diretamente
        return self._offline_latest(view, view_name, entity_id)

    def _offline_latest(self, view: dict, view_name: str, entity_id) -> dict:
        entity = self.registry["entities"][view["entity"]]
        join_key = entity["join_key"]
        ts_field = view["timestamp_field"]
        features = self._feature_names(view)
        cols = ", ".join([ts_field, *features])

        conn = self._connect()
        try:
            df = conn.execute(
                f"SELECT {cols} FROM {view['source_table']} WHERE {join_key} = ? ORDER BY {ts_field} DESC LIMIT 1",
                [entity_id],
            ).fetchdf()
        finally:
            conn.close()

        if df.empty:
            return {"entity_id": _jsonable(entity_id), "features": None, "source": "not_found"}
        row = df.to_dict(orient="records")[0]
        return {
            "entity_id": _jsonable(entity_id),
            "features": {c: _jsonable(row[c]) for c in features},
            "event_timestamp": _jsonable(row[ts_field]),
            "source": "offline_fallback",
        }

    # ---------------------------------------------------------------- freshness

    def freshness(self) -> list[dict]:
        """Idade do dado mais recente por feature view — sinal de monitoramento."""
        now = datetime.now(UTC)
        conn = self._connect()
        out = []
        try:
            for name, view in self.registry["feature_views"].items():
                ts_field = view["timestamp_field"]
                try:
                    row = conn.execute(
                        f"SELECT MAX({ts_field}) AS max_ts, COUNT(*) AS n FROM {view['source_table']}"
                    ).fetchone()
                    max_ts, n = row[0], row[1]
                except Exception:
                    max_ts, n = None, 0

                age_hours = None
                is_stale = None
                if max_ts is not None:
                    max_dt = pd.to_datetime(max_ts)
                    if max_dt.tzinfo is None:
                        max_dt = max_dt.tz_localize(UTC)
                    age_hours = round((now - max_dt.to_pydatetime()).total_seconds() / 3600, 2)
                    is_stale = age_hours > (view["online_ttl_seconds"] / 3600)

                out.append(
                    {
                        "feature_view": name,
                        "rows": int(n),
                        "latest_timestamp": _jsonable(max_ts),
                        "age_hours": age_hours,
                        "ttl_hours": round(view["online_ttl_seconds"] / 3600, 1),
                        "is_stale": is_stale,
                    }
                )
        finally:
            conn.close()
        return out

    # ------------------------------------------------------------------ catalog

    def catalog(self) -> dict:
        """Catálogo governado (entidades + views + features) para a API/portal."""
        return {
            "entities": self.registry["entities"],
            "feature_views": {
                name: {
                    "entity": v["entity"],
                    "source_table": v["source_table"],
                    "timestamp_field": v["timestamp_field"],
                    "online_ttl_seconds": v["online_ttl_seconds"],
                    "owner": v["owner"],
                    "description": v["description"],
                    "features": v["features"],
                }
                for name, v in self.registry["feature_views"].items()
            },
        }


def _jsonable(value):
    """Converte tipos numpy/pandas/date em primitivos serializáveis em JSON."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp | datetime):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    if hasattr(value, "isoformat"):  # date
        return value.isoformat()
    return value
