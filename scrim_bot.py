import discord
from discord.ext import commands
import os
from discord import app_commands

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Team channel ID where the persistent button will be located
PANEL_CHANNEL_ID = 1366433672093237310  # Replace with your actual channel ID
PANEL_MESSAGE_ID = None  # We'll track the last sent message to update it

# --- Persistent Panel with Button ---
class PersistentPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Make the view persistent (no timeout)
        
    @discord.ui.button(label="➕ Schedule Scrim", style=discord.ButtonStyle.success)
    async def schedule_scrim(self, interaction: discord.Interaction, button: discord.ui.Button):
        # When clicked, this will trigger the team selection view
        await interaction.response.send_message("Select your team:", view=TeamSelectionView(interaction.user.id), ephemeral=True)

# Team Selection View
class TeamSelectionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Affinity EMEA", style=discord.ButtonStyle.primary)
    async def select_emea(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_team(interaction, "Affinity EMEA")

    @discord.ui.button(label="Affinity Academy", style=discord.ButtonStyle.primary)
    async def select_academy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_team(interaction, "Affinity Academy")

    @discord.ui.button(label="Affinity Auras", style=discord.ButtonStyle.primary)
    async def select_auras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_team(interaction, "Affinity Auras")

    @discord.ui.button(label="Affinity NA", style=discord.ButtonStyle.primary)
    async def select_na(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_team(interaction, "Affinity NA")

    async def select_team(self, interaction: discord.Interaction, team: str):
        # Store the team data and proceed to the next step (Date and Time Modal)
        scrim_data[self.user_id] = {"team": team}
        await interaction.response.send_modal(ScrimDateTimeModal(self.user_id))

# Date and Time Modal (for team scheduling)
class ScrimDateTimeModal(discord.ui.Modal, title="Scrim Date and Time"):
    date_input = discord.ui.TextInput(
        label="Date (DD-MM-YYYY)",
        placeholder="e.g., 30-04-2025",
        required=True,
        min_length=10,
        max_length=10
    )
    time_input = discord.ui.TextInput(
        label="Time (HH:MM 24h format)",
        placeholder="e.g., 19:30",
        required=True,
        min_length=5,
        max_length=5
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Store the date/time data and proceed to the next modal
        scrim_data[self.user_id]["date"] = self.date_input.value
        scrim_data[self.user_id]["time"] = self.time_input.value
        await interaction.response.send_message(
            "Now, please enter opponent details:",
            view=OpponentDetailsView(self.user_id),
            ephemeral=True
        )

# Opponent Details Modal
class OpponentDetailsView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Enter Opponent Details", style=discord.ButtonStyle.primary)
    async def opponent_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(OpponentDetailsModal(self.user_id))

# Opponent Details Modal
class OpponentDetailsModal(discord.ui.Modal, title="Opponent Details"):
    opponent_team = discord.ui.TextInput(
        label="Opponent Team Name",
        placeholder="e.g., Team Liquid",
        required=True
    )
    opponent_rank = discord.ui.TextInput(
        label="Opponent's Average Rank",
        placeholder="e.g., Immortal 2",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Store opponent details and proceed to next steps
        scrim_data[self.user_id]["opponent_team"] = self.opponent_team.value
        scrim_data[self.user_id]["opponent_rank"] = self.opponent_rank.value
        await interaction.response.send_message(
            "Please select the match format:",
            view=FormatSelectionView(self.user_id),
            ephemeral=True
        )

# --- Setup Persistent Button on Ready ---
@bot.event
async def on_ready():
    global PANEL_MESSAGE_ID

    # Find the channel to send the persistent panel
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if not channel:
        print(f"Error: Channel with ID {PANEL_CHANNEL_ID} not found.")
        return

    # If a message already exists, try to edit it. Otherwise, send a new message.
    if PANEL_MESSAGE_ID:
        try:
            message = await channel.fetch_message(PANEL_MESSAGE_ID)
            await message.edit(content="➕ **Schedule a Scrim**", view=PersistentPanel())
            print("Updated existing panel message!")
        except (discord.NotFound, discord.HTTPException):
            print("Previous panel message not found or could not edit. Sending new panel.")
            message = await channel.send("➕ **Schedule a Scrim**", view=PersistentPanel())
            PANEL_MESSAGE_ID = message.id
    else:
        message = await channel.send("➕ **Schedule a Scrim**", view=PersistentPanel())
        PANEL_MESSAGE_ID = message.id
        print("New panel message sent!")

# --- Run Bot ---
bot.run(os.getenv("DISCORD_TOKEN"))
