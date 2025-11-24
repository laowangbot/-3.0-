
import asyncio
import logging
from unittest.mock import MagicMock
from message_engine import MessageEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_keyword_filtering_media():
    print("\n--- Test Case 1: Keyword in Media Caption ---")
    
    # Mock config
    config = {
        "filter_keywords": ["forbidden"],
        "remove_links": False,
        "enhanced_filter_enabled": False
    }
    
    engine = MessageEngine(config)
    # Mock should_process_message to always return True to focus on process_message logic
    engine.should_process_message = MagicMock(return_value=True)
    
    # Mock a media message with a keyword in caption
    message = MagicMock()
    message.id = 123
    message.text = None
    message.caption = "This is a forbidden caption"
    message.photo = True
    message.video = None
    message.document = None
    message.media = True # Simulate media presence
    
    # Process message
    print(f"Input Caption: '{message.caption}'")
    print(f"Keywords: {config['filter_keywords']}")
    
    result, should_process = await engine.process_message(message, config)
    
    print(f"Result: {result}")
    print(f"Should Process: {should_process}")
    
    # Current behavior (Bug): Text is stripped, but should_process is True because it has media
    if should_process and result.get('caption') == "":
        print("[FAIL] BUG REPRODUCED: Message text stripped but message still processed (media sent without caption).")
    elif not should_process:
        print("[PASS] FIXED: Message completely dropped.")
    else:
        print(f"[?] UNEXPECTED: {result}, {should_process}")

async def test_link_filtering_basic():
    print("\n--- Test Case 2: Basic Link Filtering (Enhanced Mode OFF) ---")
    
    # Mock config
    config = {
        "filter_keywords": [],
        "remove_links": True,
        "enhanced_filter_enabled": False # This often causes link filter to be skipped currently
    }
    
    engine = MessageEngine(config)
    engine.should_process_message = MagicMock(return_value=True)
    
    # Mock a text message with a link
    message = MagicMock()
    message.id = 124
    message.text = "Check this link: https://example.com/foo"
    message.caption = None
    message.photo = None
    message.media = None
    
    # Process message
    print(f"Input Text: '{message.text}'")
    print(f"Config: remove_links=True, enhanced_filter_enabled=False")
    
    result, should_process = await engine.process_message(message, config)
    
    processed_text = result.get('text', '')
    print(f"Processed Text: '{processed_text}'")
    
    # Current behavior (Bug): Link remains because enhanced filter is skipped
    if "https://example.com" in processed_text:
        print("[FAIL] BUG REPRODUCED: Link was NOT removed.")
    else:
        print("[PASS] FIXED: Link was removed.")

async def main():
    await test_keyword_filtering_media()
    await test_link_filtering_basic()

if __name__ == "__main__":
    asyncio.run(main())
