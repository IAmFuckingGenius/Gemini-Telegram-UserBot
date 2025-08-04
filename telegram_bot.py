import os
import asyncio
import logging
from io import BytesIO
import re
import shutil
import tempfile
import time
from telethon import TelegramClient, events
from telethon.tl.types import Message, User, Channel
from google.genai import types
import copy
from datetime import datetime
import zipfile
import mimetypes

from config import API_ID, API_HASH, PHONE, ALLOWED_GROUPS, AUTHORIZED_USER_IDS, ADMIN_USER_IDS
import gemini
import user_session_manager as usm
from history import save_history
from gemini import chat_sessions
import instruction_manager
from localization import loc
import model_manager

logging.basicConfig(format='[%(levelname)s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)
logging.getLogger('telethon').setLevel(logging.WARNING)
logger = logging.getLogger("TeleBot")

client = TelegramClient('session_name', API_ID, API_HASH)
gemini.set_telethon_client(client)

MAX_MSG_LENGTH = 4096
MAX_FILES_IN_ZIP = 1000
MAX_ZIP_DEPTH = 5
global_modes = {}

COMMANDS_CONFIG = loc.get_section("commands")
TOOL_STATUS_MESSAGES = loc.get_section("tool_statuses")
SUPPORTED_MIME_TYPES = set(loc.get_section("supported_mime_types"))

ALL_TRIGGERS = [
    trigger
    for command_config in COMMANDS_CONFIG.values()
    if command_config.get("enabled", True)
    for trigger in command_config.get("triggers", [])
]

CHATS_TO_MONITOR = list(set(ALLOWED_GROUPS + AUTHORIZED_USER_IDS + ['me']))

async def _process_zip_recursively(zip_content_bytes: bytes, media_parts: list, current_path: str = "", current_depth: int = 0):
    if current_depth > MAX_ZIP_DEPTH:
        logger.warning(loc.get_string("logs.zip_recursion_depth", depth=MAX_ZIP_DEPTH, path=current_path))
        return

    try:
        with zipfile.ZipFile(BytesIO(zip_content_bytes), 'r') as zip_archive:
            for i, file_info in enumerate(zip_archive.infolist()):
                if i >= MAX_FILES_IN_ZIP:
                    logger.warning(loc.get_string("logs.zip_file_limit", path=current_path))
                    break
                if file_info.is_dir(): continue

                full_path = os.path.join(current_path, file_info.filename)
                file_content = zip_archive.read(file_info.filename)
                if not file_content: continue
                
                mime_type, _ = mimetypes.guess_type(file_info.filename)
                
                if mime_type == 'application/zip':
                    await _process_zip_recursively(file_content, media_parts, full_path, current_depth + 1)
                else:
                    final_mime = mime_type if mime_type in SUPPORTED_MIME_TYPES else 'text/plain'
                    data_to_append = (f"--- START OF FILE: {full_path} ---\n\n".encode('utf-8') + file_content +
                                      f"\n\n--- END OF FILE: {full_path} ---".encode('utf-8')) if final_mime == 'text/plain' else file_content
                    media_parts.append(types.Part(inline_data=types.Blob(mime_type=final_mime, data=data_to_append)))
    except zipfile.BadZipFile:
        logger.warning(loc.get_string("logs.zip_bad_file", path=current_path))
    except Exception as e:
        logger.error(loc.get_string("logs.zip_process_error", path=current_path, error=e))

def extract_code_blocks_to_files(text: str, base_dir: str) -> tuple[str, list[str]]:
    pattern = re.compile(r"--- START OF FILE: (?P<filename>.+?) ---\n```(?:\w*\n)?(?P<content>.*?)```\n--- END OF FILE: (?P=filename) ---|```(?P<lang>\w*)\n(?P<md_content>.*?)\n```", re.S)
    
    created_files, new_text_parts = [], []
    last_end, counter = 0, 0

    for match in pattern.finditer(text):
        new_text_parts.append(text[last_end:match.start()])
        
        if match.group('filename'):
            filename_raw = match.group('filename').strip()
            content = match.group('content') or ""
            filepath = os.path.normpath(os.path.join(base_dir, filename_raw.lstrip('/\\')))
            if not filepath.startswith(base_dir):
                filepath = os.path.join(base_dir, os.path.basename(filename_raw))
            replacement = loc.get_string("replies.file_sent", filename=filename_raw)
        else:
            counter += 1
            lang = match.group('lang') or "txt"
            content = match.group('md_content') or ""
            filename_raw = f"code_block_{counter}.{lang}"
            filepath = os.path.join(base_dir, filename_raw)
            replacement = loc.get_string("replies.code_sent", filename=filename_raw)

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f: f.write(content.strip())
            created_files.append(filepath)
            new_text_parts.append(replacement)
        except Exception as e:
            logger.error(loc.get_string("logs.file_creation_failed", filename=filepath, error=e))
            new_text_parts.append(match.group(0))
        last_end = match.end()

    new_text_parts.append(text[last_end:])
    return "".join(new_text_parts), created_files

async def safe_reply(event, text: str, **kwargs):
    if not text or not text.strip():
        text = loc.get_string("replies.empty_response")
    
    parts = [text[i:i+MAX_MSG_LENGTH] for i in range(0, len(text), MAX_MSG_LENGTH)]
    
    msg_to_edit = event if hasattr(event, 'edit') else await event.reply(parts[0], **kwargs)
    if hasattr(event, 'edit'):
        await event.edit(parts[0])
    
    for part in parts[1:]:
        await client.send_message(event.chat_id, part, reply_to=event.id, **kwargs)

async def get_sender_info(event):
    sender = await event.get_sender()
    if isinstance(sender, User):
        return sender.id, sender.username or "", sender.first_name or f"User_{sender.id}"
    elif isinstance(sender, Channel):
        return sender.id, sender.username or "", sender.title
    return event.sender_id, "", f"Unknown_{event.sender_id}"

async def process_media(message) -> list:
    media_parts, media_source = [], message.media
    if not media_source: return media_parts
        
    for item in media_source if isinstance(media_source, list) else [media_source]:
        try:
            mime, name = ("image/jpeg", f"photo_{item.photo.id}.jpg") if hasattr(item, 'photo') else \
                         (item.document.mime_type, next((a.file_name for a in item.document.attributes if hasattr(a, 'file_name')), "doc"))
            
            buffer = BytesIO()
            await client.download_media(item, file=buffer)
            buffer.seek(0)
            content = buffer.getvalue()
            if not content:
                logger.warning(loc.get_string("logs.download_media_failed", type=type(item)))
                continue

            if mime == 'application/zip':
                await _process_zip_recursively(content, media_parts, current_path=name)
            else:
                final_mime = mime if mime in SUPPORTED_MIME_TYPES else 'text/plain'
                if final_mime == 'text/plain' and mime != 'text/plain':
                    logger.warning(loc.get_string("logs.unsupported_mime_type", mime_type=mime, filename=name))
                media_parts.append(types.Part(inline_data=types.Blob(mime_type=final_mime, data=content)))
        except Exception as e:
            logger.error(loc.get_string("logs.process_media_failed", error=e, type=type(e)))
    return media_parts

async def handle_model_command(event, prompt, sender_info):
    if sender_info[0] not in ADMIN_USER_IDS:
        return await event.reply(loc.get_string("errors.admin_only_command"))

    if not prompt:
        chat_model = model_manager.get_current_model('chat')
        image_model = model_manager.get_current_model('image')
        video_model = model_manager.get_current_model('video')
        await event.reply(loc.get_string("replies.model_current_status", chat_model=chat_model, image_model=image_model, video_model=video_model))
        return

    parts = prompt.split()
    if len(parts) != 2 or parts[0] not in ['chat', 'image', 'video']:
        await event.reply(loc.get_string("errors.model_invalid_usage", trigger=COMMANDS_CONFIG["model"]["triggers"][0]))
        return
        
    model_type, new_model = parts
    
    if model_manager.set_current_model(model_type, new_model):
        if model_type == 'chat':
            chat_sessions.clear()
            logger.info("Chat sessions cache cleared due to model change.")
        await event.reply(loc.get_string("replies.model_changed_success", type=model_type, name=new_model))
    else:
        await event.reply("Invalid model type.")

async def handle_gemini_command(event, prompt, sender_info):
    sender_id, username, first_name = sender_info
    
    if not prompt and not event.media:
        trigger = COMMANDS_CONFIG["gemini"]["triggers"][0]
        await event.reply(loc.get_string("replies.empty_user_prompt", trigger=trigger))
        return
        
    processing_msg = await event.reply(loc.get_string("replies.thinking"))

    async def status_callback(tool_name: str):
        status_text = TOOL_STATUS_MESSAGES.get(tool_name, loc.get_string("tool_statuses.default"))
        try:
            if processing_msg.text != status_text: await processing_msg.edit(status_text)
        except Exception as e: logger.warning(loc.get_string("logs.status_update_failed", error=e))

    is_global = event.is_group and global_modes.get(event.chat_id, False)
    session_key = os.path.join("histories", f"group_{abs(event.chat_id)}.json") if is_global else usm.get_active_session_path(*sender_info)
    
    gemini_parts = []
    text_to_send = f"{first_name} (@{username or sender_id}):\n\n{prompt}" if is_global and prompt else prompt
    if text_to_send: gemini_parts.append(types.Part(text=text_to_send))
    
    gemini_parts.extend(await process_media(event))
    
    answer = await gemini.call_gemini(session_key, gemini_parts, *sender_info, status_callback=status_callback)

    if answer.startswith("ACTION_SEND_FILE|"):
        try:
            _, file_path, caption = answer.split("|", 2)
            await client.send_file(event.chat_id, file_path, caption=caption, reply_to=event)
            if os.path.exists(file_path): os.remove(file_path)
            await processing_msg.delete()
        except Exception as e:
            await processing_msg.edit(loc.get_string("errors.action_file_send_error", error=e))
        return

    temp_dir = tempfile.mkdtemp()
    try:
        modified_text, files = extract_code_blocks_to_files(answer, temp_dir)
        
        if modified_text.strip(): await safe_reply(processing_msg, modified_text)
        else: await processing_msg.delete()

        for f_path in files:
            try:
                await client.send_file(event.chat_id, f_path, reply_to=event)
            except Exception as e:
                logger.error(loc.get_string("logs.file_send_failed", filename=f_path, error=e))
                await event.reply(loc.get_string("errors.reply_file_send_failed", filename=os.path.basename(f_path)))
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(loc.get_string("logs.temp_dir_deleted", dir=temp_dir))

async def handle_chat_command(event, prompt, sender_info):
    parts = prompt.split()
    subcommand = parts[0].lower() if parts else "help"
    args = parts[1:]
    
    handler_map = {
        "help": _chat_cmd_help, "list": _chat_cmd_list, "create": _chat_cmd_create,
        "switch": _chat_cmd_switch, "delete": _chat_cmd_delete, "rename": _chat_cmd_rename,
        "stats": _chat_cmd_stats
    }
    
    for cmd_key, handler_func in handler_map.items():
        if subcommand in loc.get_section(f"commands.chat.subcommands.{cmd_key}.triggers"):
            await handler_func(event, sender_info, args)
            return
            
    await event.reply(loc.get_string("errors.chat_unknown_subcommand", subcommand=subcommand, trigger=COMMANDS_CONFIG["chat"]["triggers"][0]))

async def handle_instruction_command(event, prompt, sender_info):
    sender_id, _, _ = sender_info
    parts = prompt.split(maxsplit=1)
    subcmd = parts[0].lower() if parts else "help"
    text = parts[1] if len(parts) > 1 else ""
    
    cfg = loc.get_section("commands.instruction.subcommands")

    if subcmd in cfg["set"]:
        result = instruction_manager.set_user_instruction(sender_id, text)
    elif subcmd in cfg["delete"]:
        result = instruction_manager.delete_user_instruction(sender_id)
    elif subcmd in cfg["show"]:
        await event.reply(instruction_manager.get_instruction_info(sender_id), parse_mode='md')
        return
    elif subcmd in cfg["global"] and sender_id in ADMIN_USER_IDS:
        result = instruction_manager.set_default_instruction(text)
        chat_sessions.clear()
    elif subcmd in cfg["global"]:
        await event.reply(loc.get_string("errors.admin_only_command"))
        return
    else:
        await event.reply(loc.get_string("replies.instruction_help", trigger=COMMANDS_CONFIG["instruction"]["triggers"][0]), parse_mode='md')
        return
        
    chat_sessions.pop(usm.get_active_session_path(*sender_info), None)
    await event.reply(result)

async def handle_clear_command(event, prompt, sender_info):
    session_key = usm.get_active_session_path(*sender_info)
    save_history(session_key, [])
    chat_sessions.pop(session_key, None)
    await event.reply(loc.get_string("replies.history_cleared"))

async def handle_global_mode_command(event, prompt, sender_info):
    if not event.is_group: return
    if sender_info[0] not in ADMIN_USER_IDS:
        return await event.reply(loc.get_string("errors.admin_only_command"))
    
    chat_id = event.chat_id
    
    on_triggers = loc.get_section("commands.global_mode.subcommands.on")
    off_triggers = loc.get_section("commands.global_mode.subcommands.off")

    if any(kw in prompt.lower() for kw in on_triggers):
        global_modes[chat_id] = True
        await event.reply(loc.get_string("replies.global_mode_on"))
    elif any(kw in prompt.lower() for kw in off_triggers):
        global_modes[chat_id] = False
        await event.reply(loc.get_string("replies.global_mode_off"))
    else:
        usage = loc.get_string("replies.global_mode_usage_options")
        await event.reply(loc.get_string("errors.invalid_argument_usage", command=COMMANDS_CONFIG["global_mode"]["triggers"][0], usage=usage))

async def handle_help_command(event, prompt, sender_info):
    help_text = loc.get_string("replies.main_help_header")
    for cmd_key, cmd_data in COMMANDS_CONFIG.items():
        if cmd_data.get("enabled", True):
            help_text += loc.get_string("replies.main_help_line", 
                                        triggers=" / ".join(cmd_data["triggers"]),
                                        description=cmd_data["description"])
    
    help_text += loc.get_string("replies.main_help_footer",
                                chat_trigger=COMMANDS_CONFIG["chat"]["triggers"][0],
                                instruction_trigger=COMMANDS_CONFIG["instruction"]["triggers"][0],
                                global_trigger=COMMANDS_CONFIG["global_mode"]["triggers"][0])
    await event.reply(help_text, parse_mode='md')

COMMAND_HANDLERS = {
    "gemini": handle_gemini_command,
    "chat": handle_chat_command,
    "instruction": handle_instruction_command,
    "clear": handle_clear_command,
    "global_mode": handle_global_mode_command,
    "help": handle_help_command,
    "model": handle_model_command,
}

async def _chat_cmd_help(event, sender_info, args):
    help_cfg = loc.get_section("replies.chat_help")
    subcommands_cfg = loc.get_section("commands.chat.subcommands")

    help_lines = [help_cfg['header']]
    
    for subcmd_key, description in help_cfg['lines'].items():
        triggers = subcommands_cfg.get(subcmd_key, {}).get('triggers', [])
        if triggers:
            help_lines.append(
                help_cfg['line_format'].format(triggers=" / ".join(triggers), description=description)
            )

    name = usm.get_active_session_display_name(*sender_info)
    help_lines.append(help_cfg['footer'].format(session_name=name))
    
    await event.reply("\n".join(help_lines), parse_mode='md')


async def _chat_cmd_create(event, sender_info, args):
    if not args: return await event.reply(loc.get_string("errors.argument_missing.chat_create"))
    _, msg = usm.create_session(*sender_info, " ".join(args))
    await event.reply(msg)

async def _chat_cmd_switch(event, sender_info, args):
    if not args: return await event.reply(loc.get_string("errors.argument_missing.chat_switch"))
    _, msg = usm.switch_session(*sender_info, " ".join(args))
    await event.reply(msg)

async def _chat_cmd_delete(event, sender_info, args):
    if not args: return await event.reply(loc.get_string("errors.argument_missing.chat_delete"))
    _, msg = usm.delete_session(*sender_info, " ".join(args))
    await event.reply(msg)

async def _chat_cmd_rename(event, sender_info, args):
    if len(args) < 2: return await event.reply(loc.get_string("errors.argument_missing.chat_rename"))
    _, msg = usm.rename_session(*sender_info, args[0], " ".join(args[1:]))
    await event.reply(msg)

async def _chat_cmd_list(event, sender_info, args):
    sessions = usm.get_all_sessions_info(*sender_info)
    if not sessions:
        chat_triggers = COMMANDS_CONFIG.get('chat', {}).get('triggers', ['??чат'])
        create_triggers = loc.get_section('commands.chat.subcommands.create.triggers') or ["create"]
        cmd_example = f"{chat_triggers[0]} {create_triggers[0]} <имя>"
        return await event.reply(loc.get_string("replies.chat_list_empty", example_command=cmd_example))
    
    lines = [loc.get_string("replies.chat_list_header")]
    for s in sessions:
        lines.append(loc.get_string("replies.chat_list_line",
            icon="▶️" if s["is_active"] else "📂",
            name=s['name'],
            msg_count=s['msg_count'],
            date_str=s["last_modified"].strftime('%d.%m.%y %H:%M')
        ))
    await event.reply("`" + "\n".join(lines) + "`", parse_mode='md')
    
async def _chat_cmd_stats(event, sender_info, args):
    active_s = next((s for s in usm.get_all_sessions_info(*sender_info) if s['is_active']), None)
    if not active_s: return await event.reply(loc.get_string("replies.chat_stats_no_active"))
    
    path = usm.get_active_session_path(*sender_info)
    stats = active_s.get('stats', {})
    stats_text = loc.get_string("replies.chat_stats_full",
        name=active_s.get('name', 'N/A'),
        created=datetime.fromisoformat(active_s['created_at']).strftime('%d.%m.%Y %H:%M') if active_s.get('created_at') else 'N/A',
        modified=active_s["last_modified"].strftime('%d.%m.%Y %H:%M'),
        msg_count=active_s['msg_count'],
        size_kb=os.path.getsize(path) / 1024 if path and os.path.exists(path) else 0,
        total_tokens=stats.get('total_tokens', 0),
        prompt_tokens=stats.get('prompt_tokens', 0),
        output_tokens=stats.get('output_tokens', 0),
        total_cost=stats.get('total_cost', 0.0)
    )
    await event.reply(stats_text, parse_mode='md')

async def handle_command_logic(event: Message):
    sender_info = await get_sender_info(event)
    text = event.raw_text.strip()
    
    if event.is_group and event.chat_id not in ALLOWED_GROUPS and abs(event.chat_id) not in ALLOWED_GROUPS: return
    if not event.is_group and AUTHORIZED_USER_IDS and sender_info[0] not in AUTHORIZED_USER_IDS: return

    for command_name, config in COMMANDS_CONFIG.items():
        if not config.get('enabled', True): continue
        for trigger in config.get('triggers', []):
            if text.lower().startswith(trigger):
                prompt = text[len(trigger):].strip()
                await COMMAND_HANDLERS[command_name](event, prompt, sender_info)
                return

@client.on(events.NewMessage(chats=CHATS_TO_MONITOR))
async def message_handler(event):
    if not event.raw_text or event.grouped_id:
        return
    if not any(event.raw_text.lower().startswith(trigger) for trigger in ALL_TRIGGERS):
        return
    await handle_command_logic(event.message)

@client.on(events.Album(chats=CHATS_TO_MONITOR))
async def album_handler(event):
    full_text = " ".join(m.raw_text for m in event.messages if m.raw_text).strip()
    if not any(full_text.lower().startswith(trigger) for trigger in ALL_TRIGGERS):
        logger.info(loc.get_string("logs.album_ignored_no_trigger", id=event.grouped_id))
        return

    message_for_logic = copy.copy(event.messages[0])
    message_for_logic.raw_text = full_text
    message_for_logic.message = full_text
    message_for_logic.media = event.messages
    
    logger.info(loc.get_string("logs.processing_album", id=event.grouped_id))
    await handle_command_logic(message_for_logic)

async def main():
    await client.start(phone=PHONE)
    logger.info(loc.get_string("logs.client_started"))
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info(loc.get_string("logs.script_terminated"))