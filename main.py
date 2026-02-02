from gevent import monkey
monkey.patch_all()

import asyncio
import logging
import os
import sys

# Gevent compatible loop policy for Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from steam_service import SteamService
from discord_service import DiscordBot
from database import DatabaseManager
from artist import Artist

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Main")

async def main():
    logger.info("Starting sojbot-3000...")

    # Initialize pieces
    db = DatabaseManager()
    
    # Instantiate services
    steam_service = SteamService(
        username=os.getenv("STEAM_USERNAME"),
        password=os.getenv("STEAM_PASSWORD"),
        shared_secret=os.getenv("STEAM_SHARED_SECRET")
    )
    
    artist = Artist(api_key=os.getenv("GOOGLE_API_KEY"))
    
    discord_bot = DiscordBot(
        token=os.getenv("DISCORD_TOKEN"),
        steam_service=steam_service,
        db=db,
        artist=artist
    )
    
    # We need to run both Steam and Discord loops
    # Steam.py usually blocks, so we might need to run it in a specific way or use its async capabilities if available.
    # However, steam.py is often gevent based or requires specific handling. 
    # For now, assuming we use `steam` library which has a client.
    
    # Let's start the discord bot. The steam client often needs its own thread or async handling depending on the library version.
    # We'll rely on the services to implement their run loops.
    
    await asyncio.gather(
        discord_bot.start(),
        steam_service.run()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
