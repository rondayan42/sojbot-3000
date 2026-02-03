import asyncio
import logging
import threading
import time
from steam.client import SteamClient
from steam.enums import EResult

logger = logging.getLogger("SteamService")

class SteamService:
    def __init__(self, username, password, shared_secret=None):
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.client = SteamClient()
        self.connected = False
        self.new_friend_callback = None
        self.loop = None
        
        # Setup callbacks
        self.client.on("logged_on", self.on_logged_on)
        self.client.on("disconnected", self.on_disconnected)
        self.client.on("error", self.on_error)
        self.client.on("friend_invite", self.on_friend_invite)

    def set_new_friend_callback(self, callback):
        self.new_friend_callback = callback

    def on_logged_on(self):
        self.connected = True
        logger.info(f"Logged into Steam as {self.client.user.name}")
        self.client.change_status(persona_state=1) # EPersonaState.Online
        self.client.games_played([1158310]) 

    def on_disconnected(self):
        self.connected = False
        logger.warning("Disconnected from Steam.")

    def on_error(self, result):
        logger.error(f"Steam Error: {result}")

    def on_friend_invite(self, user):
        logger.info(f"Received friend invite from {user.name} ({user.steam_id})")
        user.accept()
        logger.info(f"Accepted friend invite from {user.name}")
        
        if self.new_friend_callback and self.loop:
            asyncio.run_coroutine_threadsafe(
                self.new_friend_callback(user.steam_id, user.name), 
                self.loop
            )

    def get_rich_presence(self, steam_id):
        if not self.connected:
            return None
        user = self.client.get_user(steam_id)
        if user:
            # rich_presence is a dict on the SteamUser object in some versions, 
            # or retrieved via method. Checking typical steam.py usage:
            # It's often in user.rich_presence if available.
            return getattr(user, 'rich_presence', {})
        return None

    def add_friend(self, steam_id):
        if not self.connected:
            logger.warning("Cannot add friend: Not connected.")
            return False
        
        try:
            sid = int(steam_id)
            
            # Use generic MsgProto with the Enum
            from steam.core.msg import MsgProto
            from steam.enums.emsg import EMsg
            
            # Create the AddFriend message
            message = MsgProto(EMsg.ClientAddFriend)
            message.body.steamid_to_add = sid
            
            self.client.send(message)
            
            logger.info(f"Sent friend request to SteamID: {sid}")
            return True
        except Exception as e:
            logger.error(f"Failed to add friend {steam_id}: {e}")
            return False

    def _run_client(self):
        logger.info("Keep-alive loop for Steam Client started.")
        while True:
            try:
                if self.shared_secret:
                    # TODO: Generate 2FA code if secret provided
                    pass
                
                logger.info("Attempting to login to Steam...")
                result = self.client.login(self.username, self.password)
                
                if result != EResult.OK:
                    logger.error(f"Failed to login to Steam: {result}. Retrying in 60s...")
                    time.sleep(60)
                    continue

                logger.info("Steam Client Running...")
                self.client.run_forever()
                
                logger.warning("Steam Client disconnected. Retrying in 10s...")
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"Steam Client Crash: {e}. Restarting in 10s...")
                time.sleep(10)

    async def run(self):
        # Validate credentials before starting
        if not self.username or "your_steam_username" in self.username:
            logger.error("Invalid Steam credentials in .env! Please update them.")
            return

        self.loop = asyncio.get_running_loop()
        logger.info("Starting Steam Client Thread...")
        
        # Use a daemon thread to avoid blocking shutdown
        self.thread = threading.Thread(target=self._run_client, daemon=True)
        self.thread.start()
        
        # We don't await the thread, it runs in background.
        # But we need to keep this coroutine alive if it's gathered?
        # Actually asyncio.gather waits for all coros. 
        # If we return, gather finishes?
        # We should await an event or sleep forever to keep the service 'running' from main's perspective
        # until logical shutdown.
        
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            logger.info("Steam Service stopping...")
            self.client.logout()
