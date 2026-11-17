DEMO_ROOM_ID = "room_demo_general"
DEMO_BOT_ID = "prism_demo_bot"


def bot_client_message_id(kind: str, source_id: str) -> str:
    return f"demo-bot-{kind}-{source_id}"


def bot_processing_key(message_id: str) -> str:
    return f"prism:demo-bot:processing:{message_id}"
