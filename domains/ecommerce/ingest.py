import os
import json
import logging
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
            with open(file_path, "r", encoding="utf-8") as f:
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
    from pyspark.sql import SparkSession
    from delta import configure_spark_with_delta_pip

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
            .partitionBy("status") \
            .save(delta_path)
        logger.info("Escrita no Delta Lake via PySpark concluída com sucesso.")
        
    finally:
        logger.info("Fechando Spark Session...")
        spark.stop()

if __name__ == "__main__":
    run_ingestion()
