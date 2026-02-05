import os
import aiohttp
import logging
from typing import List, Dict, Any, Optional, Union

# Configure logging
logger = logging.getLogger(__name__)

class HTTPCursor:
    def __init__(self, client, collection_name: str, filter_query: Dict):
        self.client = client
        self.collection_name = collection_name
        self.filter_query = filter_query
        self.sort_stage = None
        self.limit_stage = None
        self.skip_stage = None
        self.projection_stage = None

    def sort(self, key_or_list, direction=None):
        """
        Mimics pymongo sort. 
        Accepts: 
        - ("field", 1)
        - [("field", 1), ("other", -1)]
        - "field" (defaults to 1)
        """
        sort_dict = {}
        
        if isinstance(key_or_list, str):
            sort_dict[key_or_list] = direction if direction is not None else 1
        elif isinstance(key_or_list, list):
            for item in key_or_list:
                if isinstance(item, tuple):
                    sort_dict[item[0]] = item[1]
                else:
                    sort_dict[item] = 1
        return self

    def limit(self, limit: int):
        self.limit_stage = limit
        return self

    def skip(self, skip: int):
        self.skip_stage = skip
        return self
        
    async def to_list(self, length: Optional[int] = None) -> List[Dict]:
        """Execute the find query via Data API"""
        payload = {
            "dataSource": self.client.cluster_name,
            "database": self.client.database_name,
            "collection": self.collection_name,
            "filter": self.filter_query,
        }
        
        if self.sort_stage:
            payload["sort"] = self.sort_stage
        
        # Data API uses 'limit' in the body
        final_limit = length
        if self.limit_stage is not None:
             # Take the smaller of the two if both exist
            final_limit = min(length, self.limit_stage) if length is not None else self.limit_stage
            
        if final_limit is not None:
            payload["limit"] = final_limit
            
        if self.skip_stage is not None:
            payload["skip"] = self.skip_stage

        response = await self.client._request("find", payload)
        return response.get("documents", [])

class HTTPCollection:
    def __init__(self, client, name: str):
        self.client = client
        self.name = name

    def find(self, filter_query: Dict = None) -> HTTPCursor:
        return HTTPCursor(self.client, self.name, filter_query or {})

    async def find_one(self, filter_query: Dict = None) -> Optional[Dict]:
        payload = {
            "dataSource": self.client.cluster_name,
            "database": self.client.database_name,
            "collection": self.name,
            "filter": filter_query or {},
        }
        response = await self.client._request("findOne", payload)
        return response.get("document")

    async def insert_one(self, document: Dict) -> Any:
        # Convert datetime objects to string if needed? 
        # Data API handles EJSON, but basic JSON is safer for start.
        # Ideally we use json_util from bson, but let's try direct first.
        
        # We need a mock InsertOneResult
        class InsertOneResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id

        payload = {
            "dataSource": self.client.cluster_name,
            "database": self.client.database_name,
            "collection": self.name,
            "document": document,
        }
        response = await self.client._request("insertOne", payload)
        return InsertOneResult(response.get("insertedId"))

    async def update_one(self, filter_query: Dict, update: Dict, upsert: bool = False) -> Any:
        class UpdateResult:
            def __init__(self, matched, modified, upserted_id=None):
                self.matched_count = matched
                self.modified_count = modified
                self.upserted_id = upserted_id

        payload = {
            "dataSource": self.client.cluster_name,
            "database": self.client.database_name,
            "collection": self.name,
            "filter": filter_query,
            "update": update,
            "upsert": upsert
        }
        response = await self.client._request("updateOne", payload)
        return UpdateResult(
            response.get("matchedCount", 0),
            response.get("modifiedCount", 0),
            response.get("upsertedId")
        )
    
    async def delete_one(self, filter_query: Dict) -> Any:
        class DeleteResult:
            def __init__(self, deleted):
                self.deleted_count = deleted
                
        payload = {
            "dataSource": self.client.cluster_name,
            "database": self.client.database_name,
            "collection": self.name,
            "filter": filter_query,
        }
        response = await self.client._request("deleteOne", payload)
        return DeleteResult(response.get("deletedCount", 0))

class AsyncMongoHTTPClient:
    def __init__(self, api_url: str, api_key: str, cluster_name: str, database_name: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.cluster_name = cluster_name
        self.database_name = database_name
        self.session = None

    def __getitem__(self, database_name):
        # Support client['db_name'] syntax, but we essentially ignore it 
        # because the HTTP client is scoped to specific config in this simplified version.
        # But to be robust:
        self.database_name = database_name
        return self

    def __getattr__(self, collection_name):
        # Support db.collection syntax
        return HTTPCollection(self, collection_name)

    async def _request(self, action: str, payload: Dict) -> Dict:
        url = f"{self.api_url}/action/{action}"
        headers = {
            "Content-Type": "application/json",
            "Access-Control-Request-Headers": "*",
            "api-key": self.api_key,
        }
        
        async with aiohttp.ClientSession() as session:
            # We create a new session per request for simplicity to avoid lifecycle issues in this hotfix
            # In production, reuse session.
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    logger.error(f"Data API Error: {resp.status} - {text}")
                    raise Exception(f"MongoDB Data API Error: {text}")
                return await resp.json()

# Helper to emulate 'db' object
class Database:
    def __init__(self, client, name):
        self.client = client
        self.name = name
    
    def __getattr__(self, collection_name):
        return HTTPCollection(self.client, collection_name)
    
    def __getitem__(self, collection_name):
        return HTTPCollection(self.client, collection_name)

