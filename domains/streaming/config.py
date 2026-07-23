"""Configuração compartilhada do pipeline de streaming (Redpanda / Kafka).

Redpanda é um broker compatível com o protocolo Kafka, então usamos o mesmo
cliente (kafka-python) apontando para o bootstrap server do Redpanda.
"""
import os

# Broker Kafka-compatível (Redpanda). No compose: "redpanda:9092".
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")

# Tópico de entrada: clickstream bruto de eventos de marketing (mídia paga).
TOPIC_MARKETING_RAW = os.environ.get("TOPIC_MARKETING_RAW", "marketing.events.raw")

# Dead-letter queue: eventos que violam o contrato de dados.
TOPIC_MARKETING_DLQ = os.environ.get("TOPIC_MARKETING_DLQ", "marketing.events.dlq")

# Consumer group do processador de stream.
CONSUMER_GROUP = os.environ.get("STREAM_CONSUMER_GROUP", "marketing-stream-processor")

# Micro-batch: a cada N eventos válidos (ou timeout) fazemos um commit no Delta Lake.
MICRO_BATCH_SIZE = int(os.environ.get("STREAM_MICRO_BATCH_SIZE", "50"))
MICRO_BATCH_TIMEOUT_SECONDS = float(os.environ.get("STREAM_MICRO_BATCH_TIMEOUT", "5.0"))
