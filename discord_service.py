import discord
from discord import app_commands
import logging
import asyncio

logger = logging.getLogger("DiscordService")

class LinkView(discord.ui.View):
    def __init__(self, bot_steam_id, discord_bot, original_interaction):
        super().__init__(timeout=300) # 5 minutes timeout
        self.discord_bot = discord_bot
        self.original_interaction = original_interaction
        
        # Add Steam URL Button
        self.add_item(discord.ui.Button(label="Add me on Steam", url=f"steam://friends/add/{bot_steam_id}"))

    async def update_with_confirmation(self, steam_id, steam_name):
        # Update the view to ask for confirmation
        self.clear_items()
        
        confirm_btn = discord.ui.Button(label=f"Yes, I am {steam_name}", style=discord.ButtonStyle.green)
        
        async def confirm_callback(interaction: discord.Interaction):
            if interaction.user.id != self.original_interaction.user.id:
                 await interaction.response.send_message("This isn't for you!", ephemeral=True)
                 return
            
            await self.discord_bot.db.add_link(interaction.user.id, steam_id)
            await interaction.response.edit_message(content=f"Successfully linked to **{steam_name}**! You can now use `/banner`.", view=None)
            # Cleanup
            if self in self.discord_bot.pending_links:
                self.discord_bot.pending_links.remove(self)

        confirm_btn.callback = confirm_callback
        self.add_item(confirm_btn)
        
        try:
            await self.original_interaction.edit_original_response(content=f"I just accepted a friend request from **{steam_name}**. Is this you?", view=self)
        except Exception as e:
            logger.error(f"Failed to update interaction: {e}")

class DiscordBot:
    def __init__(self, token, steam_service, db, artist):
        self.token = token
        self.steam_service = steam_service
        self.db = db
        self.artist = artist
        self.pending_links = [] # List of active LinkViews
        
        intents = discord.Intents.default()
        intents.message_content = True 
        
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        
        self.setup_hooks()

    def setup_hooks(self):
        @self.client.event
        async def on_ready():
            logger.info(f'Logged in as {self.client.user} (ID: {self.client.user.id})')
            await self.tree.sync()
            
            # Register callback with Steam Service
            self.steam_service.set_new_friend_callback(self.on_steam_friend_added)
        
        @self.tree.command(name="banner", description="Show your CK3 status banner")
        async def banner(interaction: discord.Interaction):
            steam_id = self.db.get_steam_id(interaction.user.id)
            
            if not steam_id:
                # Lazy Link Flow
                if not self.steam_service.client.user:
                    await interaction.response.send_message("I am currently not connected to Steam. Please try again later.", ephemeral=True)
                    return

                bot_steam_id = self.steam_service.client.user.steam_id
                view = LinkView(bot_steam_id, self, interaction)
                self.pending_links.append(view)
                await interaction.response.send_message("I need to see your game first. Click below to auto-add me on Steam.", view=view, ephemeral=True)
            else:
                await interaction.response.defer()
                
                # Get RP data
                rp = self.steam_service.get_rich_presence(steam_id)
                # rp is a dict, e.g. {'steam_display': 'King Murchad', 'param_year': '1066', ...}
                
                # Mock RP for testing if None (Remove in prod or strictly enforce)
                if not rp:
                     # Attempt to see if we can get basic info anyway
                     # But strictly, if not found, we warn.
                     # However, for testing without playing CK3, we might want a fallback? 
                     # Strictly following spec:
                     await interaction.followup.send("Could not fetch your Steam status. Are you online and playing CK3?", ephemeral=True)
                     return
                
                # Generate Prompt
                status = rp.get('steam_display', 'A medieval ruler')
                prompt = f"Oil painting, medieval dark fantasy style. Depict: {status}. High contrast, rough brushstrokes."
                
                await interaction.followup.send(f"Consulting the archives for **{status}**...")
                
                # Generate Image
                ai_image = await self.artist.generate_ai_image(prompt)
                
                # Composite
                text_data = {
                    'title': rp.get('param_title', ''),
                    'name': rp.get('param_character_name') or rp.get('steam_player_group', ''),
                    'date': rp.get('param_year', 'Unknown'),
                    'status': status,
                    'lifestyle': rp.get('param_lifestyle', '')
                }
                
                final_banner_stream = self.artist.composite(ai_image, text_data)
                
                file = discord.File(fp=final_banner_stream, filename="banner.png")
                await interaction.edit_original_response(content="", attachments=[file])

    async def on_steam_friend_added(self, steam_id, steam_name):
        logger.info(f"DiscordBot notification: New steam friend {steam_name}")
        # Notify all pending link views. 
        # In a real high-scale bot, we'd want to narrow this down, but here we can just ask everyone "Is this you?"
        # Users will ignore if it's not them.
        for view in self.pending_links[:]:
            try:
                await view.update_with_confirmation(steam_id, steam_name)
            except Exception as e:
                logger.error(f"Error updating view: {e}")
                self.pending_links.remove(view)

    async def start(self):
        logger.info("Starting Discord Client...")
        await self.client.start(self.token)
