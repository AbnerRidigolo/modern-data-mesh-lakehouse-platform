import os
import json
import logging
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from fastembed import TextEmbedding

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Qdrant_Vector_Indexing")

def main():
    # 1. Initialize Qdrant Client
    # Internal Docker communication uses "qdrant:6333", but if run locally we use "localhost:6335"
    # When running within Airflow container, QDRANT_HOST should be "qdrant" and QDRANT_PORT "6333"
    qdrant_host = os.environ.get("QDRANT_HOST", "localhost")
    qdrant_port = int(os.environ.get("QDRANT_PORT", 6335))
    
    logger.info(f"Conectando ao Qdrant em {qdrant_host}:{qdrant_port}...")
    client = QdrantClient(host=qdrant_host, port=qdrant_port)
    
    # 2. Define the product list and descriptions (5 items)
    products = [
        {
            "id": 1,
            "name": "Monitor LG 29 Ultrawide",
            "description": "Monitor LG de 29 polegadas ultrawide IPS HDMI, ideal para produtividade, programação e multitasking com tela dividida.",
            "category": "Periféricos"
        },
        {
            "id": 2,
            "name": "Teclado Mecânico Keychron",
            "description": "Teclado mecânico Keychron sem fio bluetooth com switches táteis brown, retroiluminado e ideal para digitação confortável e rápida.",
            "category": "Acessórios"
        },
        {
            "id": 3,
            "name": "Mouse Ergonômico Vertical",
            "description": "Mouse ergonômico vertical sem fio para prevenção de lesões por esforço repetitivo (LER), design anatômico e conexão bluetooth.",
            "category": "Acessórios"
        },
        {
            "id": 4,
            "name": "Fone Sony WH-1000XM4",
            "description": "Fone de ouvido Sony circum-auricular Bluetooth com cancelamento de ruído ativo premium, bateria de longa duração e áudio de alta fidelidade.",
            "category": "Áudio"
        },
        {
            "id": 5,
            "name": "Curso de Analytics Engineering",
            "description": "Curso completo de Analytics Engineering com foco em dbt, modelagem de dados moderna no DuckDB/Snowflake, governança, contratos de dados e Airflow.",
            "category": "Educação"
        }
    ]
    
    collection_name = "products"
    
    # 3. Initialize FastEmbed model
    logger.info("Inicializando modelo de embedding (FastEmbed)...")
    # By default uses BAAI/bge-small-en-v1.5 (384 dimensions)
    embedding_model = TextEmbedding()
    
    # 4. Generate Embeddings
    descriptions = [p["description"] for p in products]
    logger.info(f"Gerando embeddings para {len(descriptions)} produtos...")
    embeddings = list(embedding_model.embed(descriptions))
    vector_size = len(embeddings[0])
    logger.info(f"Embeddings gerados. Dimensão dos vetores: {vector_size}")
    
    # 5. Create Collection in Qdrant (recreates if exists to clean data)
    logger.info(f"Recriando coleção '{collection_name}' no Qdrant...")
    
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
        
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    
    # 6. Upload points to Qdrant
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
