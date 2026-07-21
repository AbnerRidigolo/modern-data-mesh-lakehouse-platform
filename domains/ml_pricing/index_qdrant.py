import logging
import os

import duckdb
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Qdrant_Vector_Indexing")

def main():
    # 1. Initialize Qdrant Client
    # Internal Docker communication uses "qdrant:6333", but if run locally we use "localhost:6335"
    qdrant_host = os.environ.get("QDRANT_HOST", "localhost")
    qdrant_port = int(os.environ.get("QDRANT_PORT", 6335))

    logger.info(f"Conectando ao Qdrant em {qdrant_host}:{qdrant_port}...")
    client = QdrantClient(host=qdrant_host, port=qdrant_port)

    # 2. Determine DuckDB Database Path
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    local_db = os.path.join(base_dir, "storage", "analytics.duckdb")
    container_db = "/opt/airflow/storage/analytics.duckdb"

    db_path = os.environ.get("DB_PATH")
    if not db_path:
        db_path = container_db if os.path.exists(container_db) else local_db

    logger.info(f"Lendo catálogo de produtos do DuckDB em: {db_path}")

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Arquivo do DuckDB não encontrado em {db_path}. Execute o dbt build primeiro.")

    # 3. Read products from DuckDB dim_products
    conn = duckdb.connect(db_path, read_only=True)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT product_id, product_name, description, category FROM dim_products")
        rows = cursor.fetchall()

        products = []
        for r in rows:
            products.append({
                "id": int(r[0]),
                "name": str(r[1]),
                "description": str(r[2]),
                "category": str(r[3])
            })
    except Exception as e:
        logger.error(f"Erro ao ler tabela dim_products do DuckDB: {e}")
        raise e
    finally:
        conn.close()

    if not products:
        logger.warning("Nenhum produto encontrado na tabela dim_products. Abortando indexação.")
        return

    logger.info(f"Carregados {len(products)} produtos para indexação.")

    collection_name = "products"

    # 4. Initialize FastEmbed model
    logger.info("Inicializando modelo de embedding (FastEmbed)...")
    embedding_model = TextEmbedding()

    # 5. Generate Embeddings
    descriptions = [p["description"] for p in products]
    logger.info(f"Gerando embeddings para {len(descriptions)} produtos...")
    embeddings = list(embedding_model.embed(descriptions))
    vector_size = len(embeddings[0])
    logger.info(f"Embeddings gerados. Dimensão dos vetores: {vector_size}")

    # 6. Create Collection in Qdrant (recreates if exists to clean data)
    logger.info(f"Recriando coleção '{collection_name}' no Qdrant...")

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )

    # 7. Upload points to Qdrant
    points = []
    for idx, p in enumerate(products):
        points.append(
            PointStruct(
                id=p["id"],
                vector=embeddings[idx].tolist(),
                payload={
                    "name": p["name"],
                    "description": p["description"],
                    "category": p["category"]
                }
            )
        )

    client.upsert(
        collection_name=collection_name,
        wait=True,
        points=points
    )

    logger.info(f"Indexação concluída com sucesso! {len(points)} produtos inseridos na coleção '{collection_name}'.")

if __name__ == "__main__":
    main()
