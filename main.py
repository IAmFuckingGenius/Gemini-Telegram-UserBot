from telegram_bot import main
import logging

logger = logging.getLogger("UserBot")

if __name__ == '__main__':
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt caught outside asyncio run (fallback).")
    finally:
        logger.info("Script execution finished.")