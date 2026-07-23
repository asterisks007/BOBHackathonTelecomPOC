"""
IBM Natural Language Understanding (NLU) client wrapper.

In mock mode (USE_MOCK=True): returns realistic entity/intent structures
with no HTTP calls.

In live mode (USE_MOCK=False): calls the real ibm-watson NLU SDK.
Lite Plan: 30,000 free calls/month — well within budget.
"""

import logging
from typing import Any, Dict, List, Optional

from core.config import get_settings

logger = logging.getLogger(__name__)

# ── Mock entity/intent library ────────────────────────────────────────────────

_MOCK_ENTITIES: Dict[str, List[Dict[str, Any]]] = {
    "fiber": [
        {"type": "Technology", "text": "fiber", "confidence": 0.95},
        {"type": "Infrastructure", "text": "junction box", "confidence": 0.88},
    ],
    "signal": [
        {"type": "Technology", "text": "4G", "confidence": 0.97},
        {"type": "IssueType", "text": "signal degradation", "confidence": 0.92},
    ],
    "5g": [
        {"type": "Technology", "text": "5G", "confidence": 0.98},
        {"type": "Technology", "text": "mmWave", "confidence": 0.85},
    ],
    "billing": [
        {"type": "Service", "text": "billing system", "confidence": 0.93},
        {"type": "IssueType", "text": "outage", "confidence": 0.91},
    ],
    "default": [
        {"type": "IssueType", "text": "network issue", "confidence": 0.70},
    ],
}

_MOCK_KEYWORDS: Dict[str, List[Dict[str, Any]]] = {
    "fiber": [
        {"text": "fiber cut", "relevance": 0.95},
        {"text": "junction box", "relevance": 0.80},
    ],
    "signal": [
        {"text": "signal degradation", "relevance": 0.92},
        {"text": "4G network", "relevance": 0.85},
    ],
    "default": [
        {"text": "network outage", "relevance": 0.75},
    ],
}


class NLUClient:
    """
    Client wrapper for IBM Watson Natural Language Understanding.

    Extracts entities, keywords, and sentiment from free-text input.
    Note: Input text must already be PII-masked before calling analyze().

    Attributes:
        use_mock: When True, returns deterministic mock NLU responses.
    """

    def __init__(self, use_mock: Optional[bool] = None) -> None:
        self._settings = get_settings()
        self.use_mock = use_mock if use_mock is not None else self._settings.use_mock

    async def analyze(self, text: str) -> Dict[str, Any]:
        """
        Analyse *text* for entities, keywords, and sentiment.

        Args:
            text: PII-masked input text to analyse.

        Returns:
            Dict with keys: entities (list), keywords (list), sentiment (dict).
        """
        if not text or not text.strip():
            return {"entities": [], "keywords": [], "sentiment": {"label": "neutral", "score": 0.0}}

        if self.use_mock:
            return self._mock_analyze(text)

        # Live path
        try:
            from ibm_watson import NaturalLanguageUnderstandingV1
            from ibm_watson.natural_language_understanding_v1 import (
                EntitiesOptions,
                Features,
                KeywordsOptions,
                SentimentOptions,
            )
            from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

            authenticator = IAMAuthenticator(self._settings.nlu_api_key)
            nlu = NaturalLanguageUnderstandingV1(version="2022-04-07", authenticator=authenticator)
            nlu.set_service_url(self._settings.nlu_url)

            response = nlu.analyze(
                text=text,
                features=Features(
                    entities=EntitiesOptions(limit=10),
                    keywords=KeywordsOptions(limit=10),
                    sentiment=SentimentOptions(),
                ),
            ).get_result()

            return {
                "entities": response.get("entities", []),
                "keywords": response.get("keywords", []),
                "sentiment": response.get("sentiment", {}).get("document", {}),
            }

        except Exception as exc:
            logger.error("NLUClient live call failed: %s", exc)
            return self._mock_analyze(text)

    def _mock_analyze(self, text: str) -> Dict[str, Any]:
        """Return mock NLU response based on keyword matching."""
        text_lower = text.lower()
        for keyword in ("fiber", "5g", "signal", "billing"):
            if keyword in text_lower:
                return {
                    "entities": _MOCK_ENTITIES.get(keyword, _MOCK_ENTITIES["default"]),
                    "keywords": _MOCK_KEYWORDS.get(keyword, _MOCK_KEYWORDS["default"]),
                    "sentiment": {"label": "negative", "score": -0.65},
                }
        return {
            "entities": _MOCK_ENTITIES["default"],
            "keywords": _MOCK_KEYWORDS["default"],
            "sentiment": {"label": "neutral", "score": -0.30},
        }
