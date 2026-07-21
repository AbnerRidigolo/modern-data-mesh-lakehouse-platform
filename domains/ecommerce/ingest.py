import json
import logging
import os
from datetime import datetime

from pydantic import ValidationError

try:
    from .contract import SaleContract
except ImportError:
    from contract import SaleContract

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ECommerce_Ingestion")

def run_ingestion():
    # Base paths
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    raw_dir = os.path.join(base_dir, "storage", "raw", "sales_data")
    delta_path = os.path.join(base_dir, "storage", "lakehouse", "ecommerce", "sales")
    quarantine_dir = os.path.join(base_dir, "storage", "raw", "quarantine", "ecommerce")

    os.makedirs(quarantine_dir, exist_ok=True)

    if not os.path.exists(raw_dir) or not os.listdir(raw_dir):
        logger.warning(f"Diretório de origem vazio ou inexistente: {raw_dir}")
        return

    valid_records = []
    invalid_count = 0

    # Read all raw JSON files
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
                    # Validate against Data Contract
                    validated = SaleContract(**record)
                    # Convert datetime to string for Spark JSON ingestion or handle manually
                    record_dict = validated.model_dump()
                    # Spark handles datetime objects if converted to isoformat string or datetime object
                    valid_records.append(record_dict)
                except ValidationError as e:
                    invalid_count += 1
                    logger.error(f"Contrato violado no registro {record.get('sale_id', 'N/A')}: {e.json()}")
                    # Save to quarantine
                    quarantine_file = os.path.join(quarantine_dir, f"error_{datetime.now().timestamp()}_{record.get('sale_id', 'unknown')}.json")
                    with open(quarantine_file, "w", encoding="utf-8") as qf:
                        json.dump({"record": record, "errors": json.loads(e.json()), "timestamp": str(datetime.now())}, qf, indent=2)

            # Archive/delete processed file
            os.remove(file_path)

        except Exception as e:
            logger.error(f"Erro ao processar arquivo {file_name}: {e}")

    logger.info(f"Processamento concluído. Válidos: {len(valid_records)}, Inválidos (Quarentena): {invalid_count}")

    if not valid_records:
        logger.info("Nenhum novo registro válido para escrever no Delta Lake.")
        return

    # E-Commerce Domain Stack: Apache Spark (PySpark)
    logger.info("Inicializando PySpark Session...")
    from delta import configure_spark_with_delta_pip
    from pyspark.sql import SparkSession

    s3_enabled = os.environ.get("AWS_ACCESS_KEY_ID") is not None
    bucket_name = "lakehouse"

    # Setup Spark with Delta Lake jars
    builder = SparkSession.builder \
        .appName("ECommerceIngestion") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .config("spark.sql.warehouse.dir", "/tmp/spark-warehouse") \
        .config("spark.sql.session.timeZone", "UTC") \
        .config("spark.driver.extraJavaOptions", "-Duser.timezone=UTC") \
        .config("spark.executor.extraJavaOptions", "-Duser.timezone=UTC") \
        .config("spark.driver.host", "localhost") \
        .config("spark.driver.bindAddress", "127.0.0.1")

    if s3_enabled:
        endpoint = os.environ.get("MINIO_ENDPOINT_URL", "http://localhost:9000")
        aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
        aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")

        builder = builder \
            .config("spark.hadoop.fs.s3a.endpoint", endpoint) \
            .config("spark.hadoop.fs.s3a.access.key", aws_access_key) \
            .config("spark.hadoop.fs.s3a.secret.key", aws_secret_key) \
            .config("spark.hadoop.fs.s3a.path.style.access", "true") \
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
            .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")

        spark = configure_spark_with_delta_pip(builder, extra_packages=["org.apache.hadoop:hadoop-aws:3.3.4"]).getOrCreate()
        delta_path = f"s3a://{bucket_name}/ecommerce/sales"

        # Ensure bucket exists
        try:
            import boto3
            from botocore.client import Config
            s3 = boto3.client(
                's3',
                endpoint_url=endpoint,
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                config=Config(signature_version='s3v4'),
                region_name='us-east-1'
            )
            try:
                s3.head_bucket(Bucket=bucket_name)
                logger.info(f"Bucket '{bucket_name}' já existe no MinIO.")
            except Exception:
                logger.info(f"Criando bucket '{bucket_name}' no MinIO...")
                s3.create_bucket(Bucket=bucket_name)
        except Exception as e:
            logger.error(f"Erro ao verificar/criar bucket S3: {e}")
    else:
        spark = configure_spark_with_delta_pip(builder).getOrCreate()

    try:
        logger.info("Convertendo registros válidos em Spark DataFrame...")
        # Spark can create DataFrame directly from list of dicts
        df = spark.createDataFrame(valid_records)

        # Write to Delta Lake partitioned by status
        logger.info(f"Gravando dados em formato Delta Lake (particionado por status) em: {delta_path}")
        df.write \
            .format("delta") \
            .mode("append") \
            .option("mergeSchema", "true") \
            .partitionBy("status") \
            .save(delta_path)
        logger.info("Escrita no Delta Lake via PySpark concluída com sucesso.")

    finally:
        logger.info("Fechando Spark Session...")
        spark.stop()

if __name__ == "__main__":
    run_ingestion()
