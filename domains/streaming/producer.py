"""Producer de clickstream de marketing em tempo real (Redpanda / Kafka).

Simula o fluxo contínuo de eventos de mídia paga que, no mundo real, chegaria de
plataformas de anúncios (Google Ads, Meta, etc.) via webhooks/SDKs. Cada evento
é publicado no tópico `marketing.events.raw`, particionado por canal para
preservar ordem por canal e permitir paralelismo no consumo.

Uso:
    python -m domains.streaming.producer --rate 5 --count 200
"""
import argparse
import json
import logging
import random
import time
from datetime import UTC, datetime

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Marketing_Stream_Producer")

CHANNELS = ["Google Ads", "Meta Ads", "Email", "Influencer"]
CATEGORY_CAMPAIGNS = {
    "Áudio": ["Fone Premium Q3", "Áudio Imersivo", "Black Friday Áudio"],
    "Periféricos": ["Setup Gamer", "Home Office Pro", "Mecânico RGB"],
    "Acessórios": ["Kit Essencial", "Acessórios Mobile", "Combo Viagem"],
    "Educação": ["Volta às Aulas", "Skills Tech", "Certificação Pro"],
}
# perfil de mídia por canal: (cpm base, ctr base)
CHANNEL_PROFILE = {
    "Google Ads": (18.0, 0.06),
    "Meta Ads": (12.0, 0.05),
    "Email": (2.0, 0.09),
    "Influencer": (25.0, 0.08),
}

# contador global de event_id para a sessão do producer (streaming range: 800000+)
_event_seq = 800000


def generate_event(inject_invalid: bool = False) -> dict:
    """Gera um evento de campanha realista. Se inject_invalid, viola o contrato
    (para exercitar a dead-letter queue do consumidor)."""
    global _event_seq
    _event_seq += 1

    channel = random.choice(CHANNELS)
    category = random.choice(list(CATEGORY_CAMPAIGNS.keys()))
    campaign = random.choice(CATEGORY_CAMPAIGNS[category])
    cpm, ctr = CHANNEL_PROFILE[channel]

    impressions = random.randint(500, 8000)
    spend = round(impressions / 1000 * cpm * random.uniform(0.8, 1.2), 2)
    clicks = int(impressions * ctr * random.uniform(0.7, 1.3))
    clicks = min(clicks, impressions)

    event = {
        "event_id": _event_seq,
        "campaign": campaign,
        "channel": channel,
        "category": category,
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
        "event_date": datetime.now(UTC).isoformat(),
    }

    if inject_invalid:
        # viola a regra clicks <= impressions para testar a DLQ
        event["clicks"] = event["impressions"] + random.randint(1, 100)

    return event


def _build_producer():
    """Cria o KafkaProducer. Import tardio para não exigir kafka-python em
    ambientes que só rodam os testes unitários (que mockam o cliente)."""
    from kafka import KafkaProducer

    return KafkaProducer(
        bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",
        retries=3,
        linger_ms=50,
    )


def run(rate: float = 5.0, count: int | None = None, invalid_ratio: float = 0.02):
    """Publica eventos no tópico a `rate` eventos/segundo. `count=None` = infinito."""
    producer = _build_producer()
    interval = 1.0 / rate if rate > 0 else 0
    sent = 0
    logger.info(
        "Producer iniciado → %s (tópico=%s, rate=%s ev/s)",
        config.KAFKA_BOOTSTRAP_SERVERS,
        config.TOPIC_MARKETING_RAW,
        rate,
    )
    try:
        while count is None or sent < count:
            event = generate_event(inject_invalid=random.random() < invalid_ratio)
            # particiona por canal → ordem preservada por canal
            producer.send(config.TOPIC_MARKETING_RAW, key=event["channel"], value=event)
            sent += 1
            if sent % 25 == 0:
                logger.info("Publicados %s eventos", sent)
            if interval:
                time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Interrompido pelo usuário.")
    finally:
        producer.flush()
        producer.close()
        logger.info("Producer finalizado. Total publicado: %s", sent)


def main():
    parser = argparse.ArgumentParser(description="Producer de clickstream de marketing (Redpanda)")
    parser.add_argument("--rate", type=float, default=5.0, help="Eventos por segundo")
    parser.add_argument("--count", type=int, default=None, help="Total de eventos (default: infinito)")
    parser.add_argument("--invalid-ratio", type=float, default=0.02, help="Fração de eventos inválidos (DLQ)")
    args = parser.parse_args()
    run(rate=args.rate, count=args.count, invalid_ratio=args.invalid_ratio)


if __name__ == "__main__":
    main()
