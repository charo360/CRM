"""
MongoDB Data API HTTP Client
Used when TUNNEL_MODE=true to connect via MongoDB Atlas Data API instead of direct TCP.
"""
import httpx
from typing import Any, Dict, List, Optional


class AsyncMongoHTTPCollection:
    def __init__(self, client: "AsyncMongoHTTPClient", db_name: str, collection: str):
        self._client = client
        self._db = db_name
        self._col = collection

    def _base(self):
        return {"dataSource": self._client.cluster, "database": self._db, "collection": self._col}

    async def _post(self, action: str, body: dict) -> dict:
        url = f"{self._client.api_url}/action/{action}"
        headers = {"api-key": self._client.api_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(url, json={**self._base(), **body}, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def find_one(self, filter: dict, projection: dict = None) -> Optional[dict]:
        body = {"filter": _encode(filter)}
        if projection:
            body["projection"] = projection
        result = await self._post("findOne", body)
        return _decode(result.get("document"))

    def find(self, filter: dict = None, sort: list = None, limit: int = 0):
        return _AsyncCursor(self, filter or {}, sort=sort, limit=limit)

    async def insert_one(self, document: dict):
        await self._post("insertOne", {"document": _encode(document)})

    async def insert_many(self, documents: List[dict]):
        await self._post("insertMany", {"documents": [_encode(d) for d in documents]})

    async def update_one(self, filter: dict, update: dict, upsert: bool = False):
        await self._post("updateOne", {"filter": _encode(filter), "update": _encode(update), "upsert": upsert})

    async def update_many(self, filter: dict, update: dict):
        await self._post("updateMany", {"filter": _encode(filter), "update": _encode(update)})

    async def delete_one(self, filter: dict):
        await self._post("deleteOne", {"filter": _encode(filter)})

    async def delete_many(self, filter: dict):
        result = await self._post("deleteMany", {"filter": _encode(filter)})
        return type("R", (), {"deleted_count": result.get("deletedCount", 0)})()

    async def count_documents(self, filter: dict) -> int:
        docs = await self.find(filter).to_list(None)
        return len(docs)

    def aggregate(self, pipeline: list):
        return _AsyncAggregateCursor(self, pipeline)

    async def create_index(self, keys, **kwargs):
        pass  # Data API does not support index creation


class _AsyncCursor:
    def __init__(self, col: AsyncMongoHTTPCollection, filter: dict, sort=None, limit=0, skip=0):
        self._col = col
        self._filter = filter
        self._sort = sort
        self._limit = limit
        self._skip = skip

    def sort(self, key_or_list, direction=None):
        if isinstance(key_or_list, list):
            self._sort = key_or_list
        else:
            self._sort = [(key_or_list, direction)]
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def skip(self, n: int):
        self._skip = n
        return self

    async def to_list(self, length: int = None) -> List[dict]:
        body: Dict[str, Any] = {"filter": _encode(self._filter)}
        if self._sort:
            body["sort"] = {k: v for k, v in self._sort}
        if self._limit:
            body["limit"] = self._limit
        if self._skip:
            body["skip"] = self._skip
        result = await self._col._post("find", body)
        docs = result.get("documents", [])
        if length is not None:
            docs = docs[:length]
        return [_decode(d) for d in docs]

    def __aiter__(self):
        self._iter_docs = None
        return self

    async def __anext__(self):
        if self._iter_docs is None:
            self._iter_docs = await self.to_list(None)
            self._iter_idx = 0
        if self._iter_idx >= len(self._iter_docs):
            raise StopAsyncIteration
        doc = self._iter_docs[self._iter_idx]
        self._iter_idx += 1
        return doc


class _AsyncAggregateCursor:
    def __init__(self, col: AsyncMongoHTTPCollection, pipeline: list):
        self._col = col
        self._pipeline = pipeline

    async def to_list(self, length: int = None) -> List[dict]:
        result = await self._col._post("aggregate", {"pipeline": _encode(self._pipeline)})
        docs = result.get("documents", [])
        if length is not None:
            docs = docs[:length]
        return [_decode(d) for d in docs]


class AsyncMongoHTTPDatabase:
    def __init__(self, client: "AsyncMongoHTTPClient", db_name: str):
        self._client = client
        self._db = db_name

    def __getattr__(self, collection: str) -> AsyncMongoHTTPCollection:
        return AsyncMongoHTTPCollection(self._client, self._db, collection)

    def __getitem__(self, collection: str) -> AsyncMongoHTTPCollection:
        return AsyncMongoHTTPCollection(self._client, self._db, collection)


class AsyncMongoHTTPClient:
    def __init__(self, api_url: str, api_key: str, cluster: str, db_name: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.cluster = cluster
        self._db_name = db_name

    def __getitem__(self, db_name: str) -> AsyncMongoHTTPDatabase:
        return AsyncMongoHTTPDatabase(self, db_name)


# ── BSON-like encode/decode ──────────────────────────────────────────────────

def _encode(obj: Any) -> Any:
    """Convert Python objects to MongoDB Data API JSON format."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_encode(i) for i in obj]
    # datetime → $date
    from datetime import datetime
    if isinstance(obj, datetime):
        return {"$date": {"$numberLong": str(int(obj.timestamp() * 1000))}}
    return obj


def _decode(obj: Any) -> Any:
    """Convert MongoDB Data API JSON format back to Python objects."""
    if obj is None:
        return None
    if isinstance(obj, list):
        return [_decode(i) for i in obj]
    if isinstance(obj, dict):
        # $date
        if "$date" in obj:
            from datetime import datetime, timezone
            ms = obj["$date"]
            if isinstance(ms, dict):
                ms = int(ms.get("$numberLong", 0))
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)
        # $oid
        if "$oid" in obj:
            return obj["$oid"]
        return {k: _decode(v) for k, v in obj.items()}
    return obj
