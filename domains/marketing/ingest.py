import json
import logging
import os
from datetime import datetime

import polars as pl
from deltalake.writer import write_deltalake
from pydantic import ValidationError

try:
    from .contract import MarketingEventContract
except ImportError:
    from contract import MarketingEventContract

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Marketing_Ingestion")


def run_ingestion():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    raw_dir = os.path.join(base_dir, "storage", "raw", "marketing_data")
    delta_path = os.path.join(base_dir, "storage", "lakehouse", "marketing", "campaigns")
    quarantine_dir = os.path.join(base_dir, "storage", "raw", "quarantine", "marketing")

    os.makedirs(quarantine_dir, exist_ok=True)

    if not os.path.exists(raw_dir) or not os.listdir(raw_dir):
        logger.warning(f"Diretório de origem vazio ou inexistente: {raw_dir}")
        return

    valid_records = []
    invalid_count = 0

    for file_name in os.listdir(raw_dir):
        if not file_name.endswith(".json"):
            continue

        file_path = os.path.join(raw_dir, file_name)
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            records = data if isinstance(data, list) else [data]
            for record in records:
                try:
                    validated = MarketingEventContract(**record)
                    valid_records.append(validated.model_dump())
                except ValidationError as e:
                    invalid_count += 1
                    logger.error(f"Contrato violado no evento {record.get('event_id', 'N/A')}: {e.json()}")
                    quarantine_file = os.path.join(
                        quarantine_dir, f"error_{datetime.now().timestamp()}_{record.get('event_id', 'unknown')}.json"
                    )
                    with open(quarantine_file, "w", encoding="utf-8") as qf:
                        json.dump({"record": record, "errors": json.loads(e.json()), "timestamp": str(datetime.now())}, qf, indent=2)

            os.remove(file_path)
        except Exception as e:
            logger.error(f"Erro ao processar arquivo {file_name}: {e}")

    logger.info(f"Processamento concluído. Válidos: {len(valid_records)}, Inválidos (Quarentena): {invalid_count}")

    if not valid_records:
        logger.info("Nenhum novo registro válido para escrever no Delta Lake.")
        return

    # Marketing Domain Stack: Polars (motor de DataFrames em Rust)
    df = pl.DataFrame(valid_records).with_columns(pl.col("event_date").cast(pl.Datetime))

    s3_enabled = os.environ.get("AWS_ACCESS_KEY_ID") is not None
    if s3_enabled:
        bucket_name = "lakehouse"
        endpoint = os.environ.get("MINIO_ENDPOINT_URL", "http://localhost:9000")
        aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
        aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")

        try:
            import boto3
            from botocore.client import Config
            s3 = boto3.client(
                "s3", endpoint_url=endpoint, aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key, config=Config(signature_version="s3v4"), region_name="us-east-1",
            )
            try:
                s3.head_bucket(Bucket=bucket_name)
            except Exception:
                s3.create_bucket(Bucket=bucket_name)
        except Exception as e:
            logger.error(f"Erro ao verificar/criar bucket S3: {e}")

        delta_path = f"s3://{bucket_name}/marketing/campaigns"
        storage_options = {
            "AWS_ACCESS_KEY_ID": aws_access_key,
            "AWS_SECRET_ACCESS_KEY": aws_secret_key,
            "AWS_ENDPOINT_URL": endpoint,
            "AWS_ALLOW_HTTP": "true",
            "AWS_S3_ALLOW_UNSAFE_SSL": "true",
        }
        logger.info(f"Escrevendo {len(df)} eventos no Delta Lake S3: {delta_path}")
        write_deltalake(delta_path, df.to_arrow(), mode="append", storage_options=storage_options)
    else:
        logger.info(f"Escrevendo {len(df)} eventos no Delta Lake local: {delta_path}")
        write_deltalake(delta_path, df.to_arrow(), mode="append")
    logger.info("Escrita concluída com sucesso.")


if __name__ == "__main__":
    run_ingestion()
