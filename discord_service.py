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
        # Discord doesn't support steam:// in buttons, so we link to the profile.
        # Ideally we'd use a redirect service, but profile is safe.
        self.add_item(discord.ui.Button(label="Add me on Steam", url=f"https://steamcommunity.com/profiles/{bot_steam_id}"))

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
            try:
                await self.tree.sync()
                logger.info("Slash commands synced.")
            except Exception as e:
                logger.error(f"Failed to sync commands: {e}")
            
            # Register callback with Steam Service
            self.steam_service.set_new_friend_callback(self.on_steam_friend_added)

        @self.client.event
        async def on_message(message):
            if message.author == self.client.user:
                return
            
            # Fallback for text commands if Slash Commands aren't showing up yet
            if message.content.startswith('/force_add'):
                try:
                    parts = message.content.split()
                    if len(parts) > 1:
                        steam_id = parts[1]
                        await message.channel.send(f"Processing force add for {steam_id}...")
                        success = self.steam_service.add_friend(steam_id)
                        if success:
                            try:
                                sid = int(steam_id)
                                await self.db.add_link(message.author.id, sid)
                                await message.channel.send(f"Request sent and link created for {sid}. Check you Steam!")
                            except:
                                await message.channel.send("Request sent.")
                        else:
                            await message.channel.send("Failed to send request (Bot offline or invalid ID).")
                    else:
                        await message.channel.send("Usage: /force_add <steam_id>")
                except Exception as e:
                    logger.error(f"Text command error: {e}")

            elif message.content.startswith('/banner'):
                 # We can't easily replicate the full interaction flow here without refactoring, 
                 # but we can give a hint.
                 await message.channel.send("Please try using the Slash Command (type `/` and select banner). If it doesn't appear, wait a few minutes or restart your Discord client.")
        
        @self.tree.command(name="force_add", description="Force the bot to add YOU on Steam (Debug)")
        async def force_add(interaction: discord.Interaction, steam_id: str):
            await interaction.response.defer(ephemeral=True)
            
            # 1. Trigger the add
            success = self.steam_service.add_friend(steam_id)
            
            if success:
                # 2. Add pending link logic so if they accept, it links?
                # Actually, if we send the request and they accept, on_friend_invite might NOT fire 
                # because on_friend_invite is for INCOMING requests. 
                # We need to listen for 'relationship' change or 'friend_added'.
                # But for now, let's just get the request sent.
                
                # We can manually create a 'pending link' expectation.
                await interaction.followup.send(f"I've sent a friend request to **{steam_id}**. Please accept it on Steam!\n\nOnce accepted, run `/banner` again to verify linking.", ephemeral=True)
                
                # We should probably optimistically link them if they say so? 
                # No, better to verify connection.
                # If they accept, we act as if we are friends. 
                # Let's simple-link them in DB if they confirm?
                # No, let's rely on event. Does 'friend_invite' fire when *they* accept *our* request? 
                # No, that's usually `relationship_change`.
                # Let's just Link them now in DB and assume they will accept. 
                # If they don't accept, RP fetch will fail gracefully.
                
                try:
                    # Basic validation that steam_id looks real
                    sid = int(steam_id)
                    await self.db.add_link(interaction.user.id, sid)
                    await interaction.followup.send(f"I've also tentatively linked your Discord to Steam ID **{sid}**. If you accept the request, `/banner` should work immediately.", ephemeral=True)
                except:
                     pass

            else:
                await interaction.followup.send("Failed to send request. Bot might be offline or ID is invalid.", ephemeral=True)

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
                
                # We put the steam:// link in text because Discord buttons don't allow it.
                # On Desktop, this link is clickable and triggers the steam client directly.
                msg = f"I need to see your game first.\n\n**Auto-Link:** steam://friends/add/{bot_steam_id}\n*(Click the link above to instantly add me)*"
                
                await interaction.response.send_message(msg, view=view, ephemeral=True)
            else:
                await interaction.response.defer()
                
                # Get RP data
                rp = self.steam_service.get_rich_presence(steam_id)
                logger.info(f"Steam RP Data for {steam_id}: {rp}")
                
                # Mock RP for testing if None (Remove in prod or strictly enforce)
                if not rp:
                     await interaction.followup.send("Could not fetch your Steam status. Are you online and playing CK3?", ephemeral=True)
                     return
                
                # Generate Prompt and Banner Text
                # Observed keys: 'steam_display': '#Singleplayer', 'character': 'Count Mordechai...', 'flavor': 'Ruling as', 'Year': '867'
                
                # Generate Prompt and Banner Text
                # Observed keys: 'steam_display': '#Singleplayer', 'character': 'Count Mordechai...', 'flavor': 'Ruling as', 'Year': '867'
                
                char_full = rp.get('character', 'Unknown Ruler')
                flavor = rp.get('flavor', '')
                year = rp.get('Year') or rp.get('param_year') or 'Unknown Year'
                
                # Attempt to split Rank from Name
                # Common CK3 ranks (English + Hebrew)
                # Sorted by length to ensure 'High Chieftain' matches before 'Chieftain', etc.
                ranks = [
                    "Melekh Ha'Melakhim", 'High Chieftain', 'Emperor', 'Basileus', 'Maharaja',
                    'Melekh', 'Sultan', 'Sheikh', 'Despot', 'Chieftain', 
                    'Count', 'Duke', 'King', 'Jarl', 'Shah', 'Doux', 'Emir', 'Raja', 
                    'Nasi', 'Rozen', 'Gaon'
                ]
                # Ensure sort by length just in case
                ranks.sort(key=len, reverse=True)
                
                rank = "Ruler"
                name_only = char_full
                
                for r in ranks:
                    if char_full.startswith(r + " "):
                        rank = r
                        name_only = char_full[len(r)+1:]
                        break
                
                # User Request:
                # Row 1: "Ruling as Mordechai of Tmutarakan" (Activity + Name)
                # Row 2: "Count" (Rank)
                # Row 3: "867" (Date)
                
                # Attempt to extract Location from Name (e.g. "Mordechai of Tmutarakan")
                if " of " in name_only:
                    parts = name_only.split(" of ", 1)
                    actual_name = parts[0]
                    location = parts[1]
                else:
                    actual_name = name_only
                    location = "Unknown Realm"

                row1 = f"{flavor} {name_only}"
                row2 = rank
                row3 = f"{year} A.D."

                # Construct Prompt
                # "Oil painting of Count Mordechai. He is the Count of Tmutarakan. Year 867. Context: Ruling."
                prompt = (
                    f"Oil painting, medieval dark fantasy style. "
                    f"Subject: {rank} {actual_name}. "
                    f"Location/Realm: {location}. "
                    f"Activity/Context: {flavor}. "
                    f"Year: {year}. "
                    f"Note: Consider the cultural origin of the name '{actual_name}' (e.g. Jewish, Germanic, etc.) for the character's ethnic appearance and attire. "
                    f"High contrast, rough brushstrokes, atmospheric lighting."
                )
                
                await interaction.followup.send(f"Consulting the archives for **{name_only}**...")
                
                # Generate Image
                ai_image = await self.artist.generate_ai_image(prompt)
                
                # Composite
                text_data = {
                    'row1': row1,
                    'row2': row2,
                    'row3': row3,
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
