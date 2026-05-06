"""Tests for backend/lambdas/chat/app.py"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from conftest import make_api_event

# ---------------------------------------------------------------------------
# Mock boto3 before importing chat (it creates a bedrock client at module level)
# ---------------------------------------------------------------------------
_mock_bedrock = MagicMock()

with patch("boto3.client", return_value=_mock_bedrock):
    from conftest import load_lambda
    app = load_lambda("chat")

handler = app.handler
is_complex_query = app.is_complex_query


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


@pytest.fixture(autouse=True)
def _reset_mock():
    _mock_bedrock.reset_mock()
    app.bedrock = _mock_bedrock


def _bedrock_response(text="Hello from Nova"):
    """Build a mock bedrock invoke_model response."""
    body_bytes = json.dumps({
        "output": {"message": {"content": [{"text": text}]}}
    }).encode()
    mock_body = MagicMock()
    mock_body.read.return_value = body_bytes
    return {"body": mock_body}


# ---------------------------------------------------------------------------
# is_complex_query() unit tests
# ---------------------------------------------------------------------------
class TestIsComplexQuery:
    def test_simple_short_query(self):
        assert is_complex_query("hi") is False

    def test_simple_medium_query(self):
        assert is_complex_query("What is the noise level in Camden?") is False

    def test_complex_compare(self):
        assert is_complex_query(
            "Can you compare Camden and Islington for families?"
        ) is True

    def test_complex_recommend(self):
        assert is_complex_query(
            "Which borough would you recommend for first time buyers?"
        ) is True

    def test_complex_budget(self):
        assert is_complex_query(
            "I have a budget of under 500k, where should I look for a flat?"
        ) is True

    def test_complex_vs(self):
        assert is_complex_query(
            "Lewisham vs Greenwich, which is better for investment growth?"
        ) is True

    def test_keyword_present_but_too_short(self):
        """A query with a keyword but under 30 chars should be simple."""
        assert is_complex_query("compare A and B") is False

    def test_long_query_without_keywords(self):
        """A long query without complex keywords should be simple."""
        assert is_complex_query(
            "Tell me about the noise levels and what it is like living there"
        ) is False

    def test_multiple_keywords(self):
        assert is_complex_query(
            "Compare the best areas for investment and recommend the top 3"
        ) is True


# ---------------------------------------------------------------------------
# handler() - routing tests
# ---------------------------------------------------------------------------
class TestHandlerRouting:
    def test_simple_query_uses_lite_model(self):
        _mock_bedrock.invoke_model.return_value = _bedrock_response()
        event = make_api_event("POST", body={
            "message": "What is noise like in Camden?",
            "history": [],
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["model"] == "lite"
        # Verify the lite model was called
        call_args = _mock_bedrock.invoke_model.call_args
        assert "nova-2-lite" in call_args[1]["modelId"]

    def test_complex_query_uses_pro_model(self):
        _mock_bedrock.invoke_model.return_value = _bedrock_response()
        event = make_api_event("POST", body={
            "message": "Compare Camden and Islington for families with young children",
            "history": [],
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        assert body["model"] == "pro"
        call_args = _mock_bedrock.invoke_model.call_args
        assert "nova-pro" in call_args[1]["modelId"]


# ---------------------------------------------------------------------------
# handler() - chat mode
# ---------------------------------------------------------------------------
class TestHandlerChat:
    def test_missing_message_returns_400(self):
        event = make_api_event("POST", body={"message": "", "history": []})
        result = handler(event, None)
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "Message is required" in body["error"]

    def test_successful_chat_response(self):
        _mock_bedrock.invoke_model.return_value = _bedrock_response("Camden is lovely.")
        event = make_api_event("POST", body={
            "message": "Tell me about Camden.",
            "history": [],
        })
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["reply"] == "Camden is lovely."

    def test_history_is_included(self):
        _mock_bedrock.invoke_model.return_value = _bedrock_response()
        event = make_api_event("POST", body={
            "message": "And what about crime?",
            "history": [
                {"role": "user", "text": "Tell me about Camden"},
                {"role": "assistant", "text": "Camden is a vibrant area..."},
            ],
        })
        handler(event, None)
        call_body = json.loads(
            _mock_bedrock.invoke_model.call_args[1]["body"]
        )
        # 2 history messages + 1 new user message = 3 total
        assert len(call_body["messages"]) == 3

    def test_viewing_context_prepended(self):
        _mock_bedrock.invoke_model.return_value = _bedrock_response()
        event = make_api_event("POST", body={
            "message": "Is this a good area?",
            "history": [],
            "context": "Camden, noise=low, score=8",
        })
        handler(event, None)
        call_body = json.loads(
            _mock_bedrock.invoke_model.call_args[1]["body"]
        )
        user_text = call_body["messages"][-1]["content"][0]["text"]
        assert "User is currently viewing" in user_text
        assert "Camden" in user_text


# ---------------------------------------------------------------------------
# handler() - insight mode
# ---------------------------------------------------------------------------
class TestHandlerInsight:
    def test_insight_mode(self):
        _mock_bedrock.invoke_model.return_value = _bedrock_response(
            "This area offers good value."
        )
        event = make_api_event("POST", body={
            "mode": "insight",
            "locationData": {
                "city": "london",
                "location": "SE1 7PB",
                "borough": "Southwark",
                "noise": "low-moderate",
                "noise_score": 4,
                "score": 7,
                "airport": "Heathrow",
                "airport_dist": 25,
                "path_dist": 12,
                "crime": "high",
                "schools": "good",
            },
        })
        result = handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["reply"] == "This area offers good value."


# ---------------------------------------------------------------------------
# CORS headers
# ---------------------------------------------------------------------------
class TestCorsHeaders:
    def test_cors_on_error(self):
        event = make_api_event("POST", body={"message": "", "history": []})
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val

    def test_cors_on_success(self):
        _mock_bedrock.invoke_model.return_value = _bedrock_response()
        event = make_api_event("POST", body={
            "message": "Hello there, tell me something.",
            "history": [],
        })
        result = handler(event, None)
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val

    def test_cors_on_500(self):
        _mock_bedrock.invoke_model.side_effect = Exception("Boom")
        event = make_api_event("POST", body={
            "message": "Hello there, tell me something.",
            "history": [],
        })
        result = handler(event, None)
        assert result["statusCode"] == 500
        for key, val in CORS_HEADERS.items():
            assert result["headers"][key] == val
