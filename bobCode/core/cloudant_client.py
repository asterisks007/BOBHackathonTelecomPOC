"""
IBM Cloudant NoSQL document store client wrapper.

In mock mode (USE_MOCK=True): uses an in-memory dict — zero network calls.
In live mode (USE_MOCK=False): calls the real Cloudant SDK.

Collections used:
  - incidents   : one document per outage event
  - tickets     : created by orchestration pipeline
  - audit_trail : append-only audit log (written by AuditLogger)
  - knowledge_base: static resolution patterns
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.config import get_settings

logger = logging.getLogger(__name__)

# In-memory store: { db_name: { doc_id: doc } }
_MOCK_STORE: Dict[str, Dict[str, Any]] = {}


def get_mock_store() -> Dict[str, Dict[str, Any]]:
    """Return reference to in-memory mock store (test inspection only)."""
    return _MOCK_STORE


def clear_mock_store() -> None:
    """Clear the in-memory mock store between tests."""
    _MOCK_STORE.clear()


class CloudantClient:
    """
    Client for IBM Cloudant NoSQL document operations.

    Attributes:
        use_mock: When True, all operations target the in-memory store.
    """

    def __init__(self, use_mock: Optional[bool] = None) -> None:
        self._settings = get_settings()
        self.use_mock = use_mock if use_mock is not None else self._settings.use_mock

    async def save(self, db_name: str, document: Dict[str, Any]) -> str:
        """
        Save a document to *db_name*, generating an _id if absent.

        Args:
            db_name:  Target collection name.
            document: Document dict to store.

        Returns:
            The document _id.
        """
        if "_id" not in document:
            document["_id"] = str(uuid.uuid4())
        if "created_at" not in document:
            document["created_at"] = datetime.now(timezone.utc).isoformat()

        if self.use_mock:
            _MOCK_STORE.setdefault(db_name, {})[document["_id"]] = document
            logger.debug("CloudantClient [MOCK] save: db=%s id=%s", db_name, document["_id"])
            return document["_id"]

        try:
            from cloudant.client import Cloudant
            client = Cloudant.iam(
                account_name=None,
                api_key=self._settings.cloudant_api_key,
                url=self._settings.cloudant_url,
                connect=True,
            )
            db = client[db_name] if db_name in client.all_dbs() else client.create_database(db_name)
            result = db.create_document(document)
            client.disconnect()
            return result["_id"]
        except Exception as exc:
            logger.error("CloudantClient save failed: %s", exc)
            # Graceful degradation to mock
            _MOCK_STORE.setdefault(db_name, {})[document["_id"]] = document
            return document["_id"]

    async def get(self, db_name: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a document by ID.

        Args:
            db_name: Target collection name.
            doc_id:  Document identifier.

        Returns:
            Document dict, or None if not found.
        """
        if self.use_mock:
            return _MOCK_STORE.get(db_name, {}).get(doc_id)

        try:
            from cloudant.client import Cloudant
            client = Cloudant.iam(
                account_name=None,
                api_key=self._settings.cloudant_api_key,
                url=self._settings.cloudant_url,
                connect=True,
            )
            doc = client[db_name][doc_id]
            client.disconnect()
            return dict(doc)
        except Exception as exc:
            logger.error("CloudantClient get failed: %s", exc)
            return None

    async def query(self, db_name: str, selector: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Query documents using a Cloudant selector.

        Args:
            db_name:  Target collection name.
            selector: Cloudant Mango query selector dict.
            limit:    Maximum documents to return.

        Returns:
            List of matching document dicts.
        """
        if self.use_mock:
            docs = list(_MOCK_STORE.get(db_name, {}).values())
            # Simple mock filter: match on top-level key equality
            results = []
            for doc in docs:
                if all(doc.get(k) == v for k, v in selector.items() if not k.startswith("$")):
                    results.append(doc)
                    if len(results) >= limit:
                        break
            return results

        try:
            from cloudant.client import Cloudant
            client = Cloudant.iam(
                account_name=None,
                api_key=self._settings.cloudant_api_key,
                url=self._settings.cloudant_url,
                connect=True,
            )
            result = client[db_name].get_query_result(selector, limit=limit)
            docs = list(result)
            client.disconnect()
            return docs
        except Exception as exc:
            logger.error("CloudantClient query failed: %s", exc)
            return []
