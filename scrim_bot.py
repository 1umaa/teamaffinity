import discord
from discord.ext import commands
import datetime
import os
import asyncio
from discord import app_commands
from typing import Dict, List, Optional, Union

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Team channel and role IDs
TEAM_CHANNELS = {
    "Affinity EMEA": 1354698542173786344,
    "Affinity Academy": 1366431756164665496,
    "Affinity Auras": 1366432079440515154,
    "Affinity NA": 1354508442135560323
}

# Define specific colors for each team channel using hexcodes
TEAM_COLORS = {
    "Affinity EMEA": discord.Color(0x12d6df),  # #12d6df - EMEA Blue
    "Affinity Academy": discord.Color(0xf70fff),  # #f70fff - ACAD Purple
    "Affinity Auras": discord.Color(0xff8cfb),  # #ff8cfb - Auras Pink
    "Affinity NA": discord.Color(0xcb0000)  # #cb0000 - NA Red
}

TEAM_ROLES = {
    "Affinity EMEA": 1354084830140436611,
    "Affinity Academy": 1354085016778575934,
    "Affinity Auras": 1354085121166278708,
    "Affinity NA": 1354085225600385044
}

ALLOWED_ROLES = [
    1354079569740824650,  # Board Member Role ID
    1354078173553365132,  # Manager role ID
    1354084742072373372,  # Team Captain Role ID
    1354280624625815773  # Coach role ID
]

# Maps selection options
MAP_OPTIONS = ["Abyss", "Ascent", "Bind", "Breeze", "Fracture", "Haven", "Icebox", "Lotus", "Pearl", "Split", "Sunset"]

# Server options
SERVER_OPTIONS = ["Frankfurt", "London", "Amsterdam", "Paris", "Warsaw", "Stockholm", "Madrid", "Virginia", "Illinois",
                  "Texas", "Oregon", "California"]

# Format options
FORMAT_OPTIONS = ["1 Game MR24", "2 Games MR24", "Best of 1", "Best of 3", "Best of 5"]

# Temporary storage (in real projects you'd use a DB)
scrim_data: Dict[int, Dict[str, Union[str, List[str]]]] = {}

# Dictionary to store scheduled reminders
# Key: unique ID for the scrim, Value: the associated task
scheduled_reminders = {}

PANEL_CHANNEL_ID = 1366433672093237310  # Replace with your actual channel ID
PANEL_MESSAGE_ID = None  # We'll track the last sent message to update it

# Persistent Panel with Button
class PersistentPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Make the view persistent (no timeout)

    @discord.ui.button(label="➕ Schedule Scrim", style=discord.ButtonStyle.success)
    async def schedule_scrim(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        scrim_data[self.user_id]["team"] = team
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
        scrim_data[self.user_id]["opponent_team"] = self.opponent_team.value
        scrim_data[self.user_id]["opponent_rank"] = self.opponent_rank.value
        await interaction.response.send_message(
            "Please select the match format:",
            view=FormatSelectionView(self.user_id),
            ephemeral=True
        )

# Format Selection View
class FormatSelectionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

        self.add_item(FormatSelector(user_id))

    async def on_timeout(self):
        if self.user_id in scrim_data:
            del scrim_data[self.user_id]

# Format Selector Dropdown
class FormatSelector(discord.ui.Select):
    def __init__(self, user_id: int):
        self.user_id = user_id

        options = [
            discord.SelectOption(label=format_option, value=format_option)
            for format_option in FORMAT_OPTIONS
        ]

        super().__init__(
            placeholder="Select match format...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_format = self.values[0]
        scrim_data[self.user_id]["format"] = selected_format

        await interaction.response.send_message(
            "Please select the maps to be played:",
            view=MapSelectionView(self.user_id),
            ephemeral=True
        )

# Map Selection View
class MapSelectionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

        self.add_item(MapSelector(user_id))

    async def on_timeout(self):
        if self.user_id in scrim_data:
            del scrim_data[self.user_id]

# Map Selector Dropdown
class MapSelector(discord.ui.Select):
    def __init__(self, user_id: int):
        self.user_id = user_id

        options = [
            discord.SelectOption(label=map_name, value=map_name)
            for map_name in MAP_OPTIONS
        ]

        super().__init__(
            placeholder="Select maps...",
            min_values=1,
            max_values=5,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_maps = self.values
        scrim_data[self.user_id]["maps"] = selected_maps

        await interaction.response.send_message(
            "Please select the server:",
            view=ServerSelectionView(self.user_id),
            ephemeral=True
        )

# Server Selection View
class ServerSelectionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

        self.add_item(ServerSelector(user_id))

    async def on_timeout(self):
        if self.user_id in scrim_data:
            del scrim_data[self.user_id]

# Server Selector Dropdown
class ServerSelector(discord.ui.Select):
    def __init__(self, user_id: int):
        self.user_id = user_id

        options = [
            discord.SelectOption(label=server, value=server)
            for server in SERVER_OPTIONS
        ]

        super().__init__(
            placeholder="Select server location...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_server = self.values[0]
        scrim_data[self.user_id]["server"] = selected_server

        await interaction.response.send_message(
            "Please enter the players:",
            view=PlayerSelectionView(self.user_id),
            ephemeral=True
        )

# Player Selection View
class PlayerSelectionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Enter Players", style=discord.ButtonStyle.primary)
    async def add_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerSelectionModal(self.user_id))

    async def on_timeout(self):
        if self.user_id in scrim_data:
            del scrim_data[self.user_id]

# Player Selection Modal
class PlayerSelectionModal(discord.ui.Modal, title="Player Selection"):
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

    players_input = discord.ui.TextInput(
        label="Players (one per line)",
        style=discord.TextStyle.paragraph,
        placeholder="@Player1\n@Player2\n@Player3\n@Player4\n@Player5",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        players = self.players_input.value.strip().split('\n')
        scrim_data[self.user_id]["players"] = players

        embed = generate_preview_embed(self.user_id)

        await interaction.response.send_message(
            "Here's a preview of your scrim announcement:",
            embed=embed,
            view=ConfirmationView(self.user_id),
            ephemeral=True
        )

# Confirmation View
class ConfirmationView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Confirm & Send", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_scrim_announcement(self.user_id, interaction)

        await interaction.response.send_message(
            "✅ Scrim announcement confirmed and sent! A reminder will be sent 30 minutes before the scrim starts.",
            ephemeral=True
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id in scrim_data:
            del scrim_data[self.user_id]

        await interaction.response.send_message(
            "❌ Scrim announcement cancelled.",
            ephemeral=True
        )

    async def on_timeout(self):
        if self.user_id in scrim_data:
            del scrim_data[self.user_id]

# Generate preview embed for the scrim
def generate_preview_embed(user_id: int) -> discord.Embed:
    data = scrim_data[user_id]
    team = data["team"]

    date_time_str = f"{data['date']} {data['time']}"
    try:
        date_time_obj = datetime.datetime.strptime(date_time_str, "%d-%m-%Y %H:%M")
        unix_timestamp = int(date_time_obj.timestamp())
    except ValueError:
        unix_timestamp = int(datetime.datetime.now().timestamp())

    players_formatted = '\n'.join(f"- {player}" for player in data['players'])

    maps_value = data.get("maps", [])
    if isinstance(maps_value, list):
        maps_text = '\n'.join(f"- {map_name}" for map_name in maps_value)
    else:
        maps_text = str(maps_value)

    color = TEAM_COLORS.get(team, discord.Color(0x3498DB)) 

    embed = discord.Embed(
        title=f"🛡️ {team} Scrim Scheduled",
        color=color
    )

    embed.add_field(name="📅 Date & Time", value=f"<t:{unix_timestamp}:F>", inline=False)
    embed.add_field(name="🏴 Opponent", value=data["opponent_team"], inline=False)
    embed.add_field(name="🎯 Opponent Rank", value=data["opponent_rank"], inline=False)
    embed.add_field(name="📖 Format", value=data["format"], inline=False)
    embed.add_field(name="🗺️ Maps", value=maps_text, inline=False)
    embed.add_field(name="🌍 Server", value=data["server"], inline=False)
    embed.add_field(name="👥 Players", value=players_formatted, inline=False)
    embed.add_field(name="⏰ Reminder", value="A reminder will be sent 30 minutes before the scrim starts.", inline=False)

    return embed

# Send scrim announcement to the proper channel
async def send_scrim_announcement(user_id: int, interaction: discord.Interaction) -> None:
    data = scrim_data[user_id]
    team = data["team"]

    channel_id = TEAM_CHANNELS.get(team)
    role_id = TEAM_ROLES.get(team)

    if not channel_id:
        await interaction.followup.send(
            f"❌ Error: Could not find channel for team {team}",
            ephemeral=True
        )
        return

    embed = generate_preview_embed(user_id)

    channel = bot.get_channel(channel_id)
    if not channel:
        await interaction.followup.send(
            f"❌ Error: Could not find channel with ID {channel_id}",
            ephemeral=True
        )
        return

    content = (f"# <@&{role_id}> Scrim scheduled! "
               f"Please review the below and reach out to your Team Captain if you won't be available, so that we can find a substitute")

    await channel.send(content=content, embed=embed)

    date_time_obj = data.get("date_time_obj")
    if date_time_obj:
        await schedule_reminder(
            team=team,
            opponent_team=data["opponent_team"],
            date_time_obj=date_time_obj,
            channel_id=channel_id,
            role_id=role_id,
            players=data["players"]
        )

    del scrim_data[user_id]

# Ready Event
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
        print(f"Logged in as {bot.user}")
    except Exception as e:
        print(f"Error syncing commands: {e}")

    await setup_persistent_button()

# Set up persistent button in the specified channel
async def setup_persistent_button():
    global PANEL_MESSAGE_ID
    channel = bot.get_channel(PANEL_CHANNEL_ID)

    if not channel:
        print(f"Error: Channel with ID {PANEL_CHANNEL_ID} not found.")
        return

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
