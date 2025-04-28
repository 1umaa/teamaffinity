import discord
from discord.ext import commands, tasks
import datetime, time
import os

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

PANEL_CHANNEL_ID = 1366433672093237310  # replace with your real channel ID
PANEL_MESSAGE_ID = None  # We'll dynamically track it

# Team channel and role IDs (replace with your real IDs)
TEAM_CHANNELS = {
    "Affinity EMEA 🇪🇺": 1354698542173786344,
    "Affinity Academy 🇪🇺": 1366431756164665496,
    "Affinity Auras 🇪🇺": 1366432079440515154,
    "Affinity NA 🇺🇸": 1354508442135560323
}

TEAM_ROLES = {
    "Affinity EMEA 🇪🇺": 1354084830140436611,
    "Affinity Academy 🇪🇺": 1354085016778575934,
    "Affinity Auras 🇪🇺": 1354085121166278708,
    "Affinity NA 🇺🇸": 1354085225600385044
}

ALLOWED_ROLES = [
    1354079569740824650,  # Board Member Role ID
    1354078173553365132,  # Manager role ID
    1354084742072373372,  # Team Captain Role ID
    1354280624625815773  # Coach role ID
]

# Temporary storage (in real projects you'd use a DB)
scrim_data = {}
scheduled_scrims = []


class PersistentPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)  # Increased timeout
        self.clear_items()  # Reset the view
        self.add_item(TeamDropdown())  # Add the dropdown here

    @discord.ui.button(label="➕ Schedule Scrim", style=discord.ButtonStyle.success)
    async def schedule_scrim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()  # Defer the interaction
        await interaction.followup.send("Select the team for this scrim:", view=TeamSelect(), ephemeral=True)


class TeamSelect(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Timeout None for persistent view
        self.clear_items()  # Ensure only one item is added
        self.add_item(TeamDropdown())  # Add the TeamDropdown here


class TeamDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Affinity EMEA 🇪🇺"),
            discord.SelectOption(label="Affinity Academy 🇪🇺"),
            discord.SelectOption(label="Affinity Auras 🇪🇺"),
            discord.SelectOption(label="Affinity NA 🇺🇸")
        ]
        super().__init__(
            placeholder="Select the team for this scrim",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        scrim_data[user_id] = {"team": self.values[0]}

        # Defer interaction and then open the modal
        await interaction.response.defer()  # Defer the interaction
        await interaction.response.send_modal(ScrimModal())  # Open the modal correctly

class ScrimModal(discord.ui.Modal, title="Schedule a Scrim"):
    scrim_date = discord.ui.TextInput(
        label="Scrim Date (DD-MM-YYYY)",
        placeholder="01-05-2025",
        required=True
    )
    scrim_time = discord.ui.TextInput(
        label="Scrim Time (HH:MM 24h format)",
        placeholder="19:00",
        required=True
    )
    opponent_team = discord.ui.TextInput(
        label="Opponent Team Name",
        placeholder="Team Nebula Rising",
        required=True
    )
    opponent_rank = discord.ui.TextInput(
        label="Opponent Average Rank",
        placeholder="Ascendant 2",
        required=True
    )
    format = discord.ui.TextInput(
        label="Format",
        placeholder="Best of 3",
        required=True
    )
    maps = discord.ui.TextInput(
        label="Maps",
        placeholder="Ascent, Sunset, Bind",
        required=True
    )
    server = discord.ui.TextInput(
        label="Server",
        placeholder="Texas 1",
        required=True
    )
    players = discord.ui.TextInput(
        label="Players (Mentioned @players)",
        placeholder="@Player1 @Player2 @Player3",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        scrim_data[user_id] = {
            "date": self.scrim_date.value.strip(),
            "time": self.scrim_time.value.strip(),
            "opponent_team": self.opponent_team.value.strip(),
            "opponent_rank": self.opponent_rank.value.strip(),
            "format": self.format.value.strip(),
            "maps": self.maps.value.strip(),
            "server": self.server.value.strip(),
            "players": self.players.value.strip()
        }
        await interaction.response.send_message(
            embed=generate_preview_embed(user_id),
            view=ConfirmView(user_id),
            ephemeral=True
        )


# --- Run Bot ---
bot.run(os.getenv("DISCORD_TOKEN"))
