from config import HISTORY_SOURCE_GROUPS
import logging
from telethon import TelegramClient
from localization import loc

logger = logging.getLogger("group_history_tool")

async def get_combined_group_history(client: TelegramClient, group_names: list[str] | None = None, num_messages: int = 100) -> str:
    """
    Collects message history from specified Telegram groups.

    Args:
        client: Active Telethon client.
        group_names: List of group names to search for. If not specified, all groups from the config are used.
        num_messages: Number of latest messages to retrieve from each group.

    Returns:
        A string containing the formatted message history from the found groups.
    """
    logger.info(loc.get_string("logs.history_collection_started", groups=group_names, count=num_messages))
    
    if num_messages > 15000:
        num_messages = 15000

    all_history_lines = []
    
    target_group_ids = []
    if group_names:
        async for dialog in client.iter_dialogs():
            if dialog.is_group and dialog.title in group_names:
                if dialog.id in HISTORY_SOURCE_GROUPS:
                    target_group_ids.append(dialog.id)
    else:
        target_group_ids = HISTORY_SOURCE_GROUPS

    if not target_group_ids:
        return loc.get_string("errors.history_no_groups_found")

    for group_id in target_group_ids:
        try:
            group_entity = await client.get_entity(group_id)
            group_name = getattr(group_entity, "title", str(group_id))
            
            header = loc.get_string("replies.history_group_header", name=group_name, id=group_id)
            all_history_lines.append(header)
            
            messages = await client.get_messages(group_id, limit=num_messages)
            if not messages:
                all_history_lines.append(loc.get_string("replies.history_no_messages_in_group"))
                continue

            for msg in reversed(messages):
                if not msg or not msg.message:
                    continue

                sender = await msg.get_sender()
                sender_name = loc.get_string("replies.history_unknown_sender")
                if sender:
                    if hasattr(sender, 'title') and sender.title:
                        sender_name = sender.title
                    elif hasattr(sender, 'first_name') and sender.first_name:
                        sender_name = sender.first_name
                    else:
                        id_prefix = loc.get_string("replies.history_sender_id_prefix")
                        sender_name = getattr(sender, 'username', f"{id_prefix}{sender.id}")
                
                timestamp = msg.date.strftime("%H:%M")
                text_content = msg.raw_text.strip() if msg.raw_text else ""
                
                if msg.media:
                    text_content += f" [{loc.get_string('replies.history_media_tag')}]"

                if text_content:
                    line = f"[{timestamp}] {sender_name}: {text_content}"
                    all_history_lines.append(line)
        
        except Exception as e:
            logger.error(loc.get_string("logs.history_collection_error", group_id=group_id, error=e))
            all_history_lines.append(loc.get_string("errors.history_collection_failed_for_group", group_id=group_id))

    return "\n".join(all_history_lines)
