import os
import json
import logging
import polars as pl
from datetime import datetime
from pydantic import ValidationError
from deltalake.writer import write_deltalake
try:
    from .contract import CustomerContract
except ImportError:
    from contract import CustomerContract

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("CRM_Ingestion")

def run_ingestion():
    # Base paths
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    raw_dir = os.path.join(base_dir, "storage", "raw", "customers_data")
    delta_path = os.path.join(base_dir, "storage", "lakehouse", "crm", "customers")
    quarantine_dir = os.path.join(base_dir, "storage", "raw", "quarantine", "crm")
    
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
                
            # Data can be a single dict or list of dicts
            records = data if isinstance(data, list) else [data]
            
            for record in records:
                try:
                    # Validate against Data Contract
                    validated = CustomerContract(**record)
                    # Store as python dict
                    valid_records.append(validated.model_dump())
                except ValidationError as e:
                    invalid_count += 1
                    logger.error(f"Contrato violado no registro {record.get('id', 'N/A')}: {e.json()}")
                    # Save to quarantine
                    quarantine_file = os.path.join(quarantine_dir, f"error_{datetime.now().timestamp()}_{record.get('id', 'unknown')}.json")
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

    # Convert to Polars DataFrame (CRM Domain Stack: Polars)
    df = pl.DataFrame(valid_records)
    
    # Cast created_at to timestamp (Delta Lake/Parquet compatibility)
    df = df.with_columns(pl.col("created_at").cast(pl.Datetime))

    # Write Polars DataFrame to Delta Lake
    logger.info(f"Escrevendo {len(df)} registros no Delta Lake: {delta_path}")
    
    # write_deltalake takes pandas DataFrame or Arrow table. Polars to_arrow() is zero-copy
    write_deltalake(
        delta_path,
        df.to_arrow(),
        mode="append"
    )
    logger.info("Escrita concluída com sucesso.")

if __name__ == "__main__":
    run_ingestion()
