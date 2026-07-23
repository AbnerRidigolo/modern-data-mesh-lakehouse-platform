"""Stream processor: consome o clickstream de marketing do Redpanda, valida cada
evento contra o contrato de dados e micro-batcha os eventos válidos para o Delta
Lake (mesma tabela do batch: `marketing/campaigns`). Eventos que violam o
contrato vão para a dead-letter queue (`marketing.events.dlq`).

Arquitetura em duas camadas para testabilidade:
  - `validate_records` / `partition_batch`: funções puras, testáveis sem broker.
  - `StreamProcessor.run`: laço de consumo real (Kafka), fino, orquestra as
    funções puras + escrita no Delta.

Uso:
    python -m domains.streaming.consumer
"""
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

import polars as pl
from deltalake.writer import write_deltalake
from pydantic import ValidationError

from domains.common.paths import (
    get_delta_storage_options,
    get_delta_table_path,
    s3_enabled,
)
from domains.marketing.contract import MarketingEventContract

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Marketing_Stream_Consumer")


@dataclass
class BatchResult:
    valid: list = field(default_factory=list)
    invalid: list = field(default_factory=list)  # [(raw_record, error_message)]


def validate_record(raw: dict) -> tuple[dict | None, str | None]:
    """Valida um evento contra o contrato. Retorna (dump_validado, None) ou
    (None, mensagem_de_erro)."""
    try:
        model = MarketingEventContract(**raw)
        return model.model_dump(), None
    except ValidationError as e:
        return None, e.json()
    except (TypeError, ValueError) as e:
        return None, str(e)


def partition_batch(records: list) -> BatchResult:
    """Separa uma lista de eventos crus em válidos e inválidos (função pura)."""
    result = BatchResult()
    for raw in records:
        validated, error = validate_record(raw)
        if validated is not None:
            result.valid.append(validated)
        else:
            result.invalid.append((raw, error))
    return result


def flush_to_delta(valid_records: list) -> int:
    """Micro-batch append no Delta Lake da marketing. Retorna nº de linhas escritas."""
    if not valid_records:
        return 0

    df = pl.DataFrame(valid_records).with_columns(pl.col("event_date").cast(pl.Datetime))
    delta_path = get_delta_table_path("marketing_campaigns")

    if s3_enabled():
        write_deltalake(delta_path, df.to_arrow(), mode="append", storage_options=get_delta_storage_options())
    else:
        os.makedirs(os.path.dirname(delta_path), exist_ok=True)
        write_deltalake(delta_path, df.to_arrow(), mode="append")

    logger.info("Micro-batch escrito no Delta Lake: %s eventos → %s", len(df), delta_path)
    return len(df)


class StreamProcessor:
    """Orquestra consumo → validação → micro-batch → Delta / DLQ."""

    def __init__(self, producer=None):
        # producer opcional para publicar na DLQ (injetável em teste)
        self._dlq_producer = producer

    def _build_consumer(self):
        from kafka import KafkaConsumer

        return KafkaConsumer(
            config.TOPIC_MARKETING_RAW,
            bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
            group_id=config.CONSUMER_GROUP,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            consumer_timeout_ms=int(config.MICRO_BATCH_TIMEOUT_SECONDS * 1000),
        )

    def _build_dlq_producer(self):
        if self._dlq_producer is not None:
            return self._dlq_producer
        from kafka import KafkaProducer

        self._dlq_producer = KafkaProducer(
            bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        return self._dlq_producer

    def _send_to_dlq(self, invalid: list):
        if not invalid:
            return
        producer = self._build_dlq_producer()
        for raw, error in invalid:
            payload = {"record": raw, "error": error, "quarantined_at": datetime.now(UTC).isoformat()}
            producer.send(config.TOPIC_MARKETING_DLQ, value=payload)
        producer.flush()
        logger.warning("Enviados %s eventos inválidos para a DLQ (%s)", len(invalid), config.TOPIC_MARKETING_DLQ)

    def run(self, max_batches: int | None = None):
        """Laço de consumo. `max_batches` limita o nº de micro-batches (para demos)."""
        consumer = self._build_consumer()
        logger.info(
            "Consumer iniciado ← %s (tópico=%s, grupo=%s)",
            config.KAFKA_BOOTSTRAP_SERVERS,
            config.TOPIC_MARKETING_RAW,
            config.CONSUMER_GROUP,
        )
        buffer: list = []
        batches_done = 0
        try:
            while True:
                got_message = False
                for message in consumer:
                    got_message = True
                    buffer.append(message.value)
                    if len(buffer) >= config.MICRO_BATCH_SIZE:
                        break

                if buffer:
                    result = partition_batch(buffer)
                    flush_to_delta(result.valid)
                    self._send_to_dlq(result.invalid)
                    consumer.commit()
                    buffer = []
                    batches_done += 1
                    if max_batches is not None and batches_done >= max_batches:
                        break

                # consumer_timeout_ms encerra a iteração do for quando ocioso
                if not got_message and max_batches is not None:
                    break
        except KeyboardInterrupt:
            logger.info("Interrompido pelo usuário.")
        finally:
            if buffer:
                result = partition_batch(buffer)
                flush_to_delta(result.valid)
                self._send_to_dlq(result.invalid)
                consumer.commit()
            consumer.close()
            logger.info("Consumer finalizado. Micro-batches processados: %s", batches_done)


def main():
    StreamProcessor().run()


if __name__ == "__main__":
    main()
