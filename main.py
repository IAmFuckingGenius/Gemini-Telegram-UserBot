from localization import loc
loc.initialize()
from telegram_bot import main
import logging

logger = logging.getLogger("UserBot")

if __name__ == '__main__':
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info(loc.get_string("logs.script_terminated_by_user"))
    finally:
        logger.info(loc.get_string("logs.script_execution_finished"))
