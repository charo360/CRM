"""Unit tests for email contact classification and reply draft auto-generation."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from email_classifier import EmailContactClassifier


@pytest.mark.anyio
async def test_email_classification_and_auto_drafting(anyio_backend):
    if anyio_backend != "asyncio":
        pytest.skip("Only supports asyncio backend due to asyncio.to_thread")
        
    db = AsyncMock()
    
    # Mock find_one for business info
    db.users.find_one = AsyncMock(return_value={
        "_id": "user-123",
        "business_name": "My Boutique",
        "business_type": "Clothing Store"
    })
    
    # Mock find_one for existing customer (None means new customer)
    db.customers.find_one = AsyncMock(return_value=None)
    
    # Mock database insert/update operations
    db.customers.insert_one = AsyncMock()
    db.pending_email_classifications.update_one = AsyncMock()
    db.email_messages.update_many = AsyncMock()
    db.email_messages.update_one = AsyncMock()
    
    # Mock find cursor for unclassified email messages with chained calls
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "_id": "msg-123",
            "thread_id": "thread-123",
            "from_addr": "buyer@example.com",
            "to_addr": "boutique@zilo.pro",
            "subject": "inquiry about dress size",
            "body_clean": "Hi, do you have the blue dress in size M?",
            "provider": "gmail",
            "is_outgoing": False
        }
    ])
    db.email_messages.find = MagicMock(return_value=mock_cursor)
    
    # Setup Email classifier
    classifier = EmailContactClassifier(db)
    
    # Mock OpenAI client
    mock_openai = MagicMock()
    classifier.client = mock_openai
    classifier.has_ai = True
    
    # First OpenAI call (classification): TYPE: customer
    mock_class_choice = MagicMock()
    mock_class_choice.message.content = "TYPE: customer\nCONFIDENCE: 0.95\nREASON: Inquiry about dress size\nSUBTYPE: Lead"
    mock_class_response = MagicMock()
    mock_class_response.choices = [mock_class_choice]
    
    # Second OpenAI call (auto-draft reply)
    mock_draft_choice = MagicMock()
    mock_draft_choice.message.content = "Hi there! Yes, we have the blue dress in stock in size M. Let me know if you would like me to set it aside for you."
    mock_draft_response = MagicMock()
    mock_draft_response.choices = [mock_draft_choice]
    
    # Patch the mock client completions create method to return class then draft
    with patch.object(mock_openai.chat.completions, "create", side_effect=[mock_class_response, mock_draft_response]):
        # Mock Composio execute action / proxy
        with patch("composio_service.composio_proxy", AsyncMock(return_value={"id": "draft-abc12345"})) as mock_proxy:
            
            stats = await classifier.classify_new_emails("user-123")
            
            # Verify classification results
            assert stats["classified"] == 1
            assert stats["created"] == 1
            
            # Verify Composio draft proxy was called to save the draft
            mock_proxy.assert_called_once()
            args, kwargs = mock_proxy.call_args
            assert args[0] == "user-123"
            assert args[1] == "gmail"
            assert args[2] == "POST"
            assert args[3] == "gmail/v1/users/me/drafts"
            
            # Verify database updates
            db.customers.insert_one.assert_called_once()
            db.email_messages.update_one.assert_called_once()
            # Verify mark message as reply_drafted: True
            assert db.email_messages.update_one.call_args[0][0] == {"_id": "msg-123"}
            assert db.email_messages.update_one.call_args[0][1] == {"$set": {"reply_drafted": True}}
