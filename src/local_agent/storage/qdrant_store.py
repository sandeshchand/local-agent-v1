from __future__ import annotations

from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


class QdrantStore:
    def __init__(self, storage_path: str | Path, collection_name: str = "knowledge_chunks") -> None:
        self.storage_path = Path(storage_path).expanduser().resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.client: QdrantClient | None = None

    def connect(self) -> QdrantClient:
        if self.client is None:
            self.client = QdrantClient(path=str(self.storage_path))
        return self.client

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def initialize_collection(self, vector_size: int) -> None:
        client = self.connect()

        if not self.collection_exists():
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )

    def health_check(self) -> bool:
        client = self.connect()
        collections = client.get_collections().collections
        return isinstance(collections, list)

    def collection_exists(self) -> bool:
        client = self.connect()
        collections = client.get_collections().collections
        collection_names = {collection.name for collection in collections}
        return self.collection_name in collection_names

    def upsert_test_vector(
        self,
        point_id: int,
        vector: list[float],
        payload: dict[str, Any] | None = None,
    ) -> None:
        client = self.connect()
        client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload or {},
                )
            ],
        )

    def search_test_vector(self, query_vector: list[float], limit: int = 3):
        client = self.connect()
        return client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
        )

    def upsert_chunks(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return

        client = self.connect()
        points = [
            PointStruct(
                id=record["id"],
                vector=record["vector"],
                payload=record["payload"],
            )
            for record in records
        ]
        client.upsert(collection_name=self.collection_name, points=points)

    def search(self, query_vector: list[float], limit: int = 5,doc_id:str = None):
        if not self.collection_exists():
            return _EmptyQueryResult()

        client = self.connect()
        query_filter = None
        
        if doc_id:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="doc_id",
                        match=MatchValue(value=doc_id),
                    ),
                ]
            )

        return client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )


class _EmptyQueryResult:
    points: list[Any] = []
