import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path="sojbot.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS links (
                discord_id INTEGER PRIMARY KEY,
                steam_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("Database initialized.")

    def get_steam_id(self, discord_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT steam_id FROM links WHERE discord_id = ?", (discord_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    def add_link(self, discord_id, steam_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("INSERT OR REPLACE INTO links (discord_id, steam_id, created_at) VALUES (?, ?, ?)",
                      (discord_id, steam_id, datetime.now()))
            conn.commit()
            logger.info(f"Linked Discord ID {discord_id} to Steam ID {steam_id}")
        except Exception as e:
            logger.error(f"Error linking user: {e}")
        finally:
            conn.close()
