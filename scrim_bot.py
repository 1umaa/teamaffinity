import discord
from discord.ext import commands, tasks
from discord import app_commands
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
    1354079569740824650,    # Board Member Role ID
    1354078173553365132,    # Manager role ID
    1354084742072373372,    # Team Captain Role ID
    1354280624625815773     # Coach role ID
]

# Temporary storage (in real projects you'd use a DB)
scrim_data = {}
scheduled_scrims = []

class PersistentPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)  # Increased timeout to 5 minutes
        self.clear_items()  # Ensure we reset the view each time
        self.add_item(TeamDropdown())

    @discord.ui.button(label="➕ Schedule Scrim", style=discord.ButtonStyle.success)
    async def schedule_scrim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Select the team for this scrim:", view=TeamSelect(), ephemeral=True)

class TeamSelect(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Keep timeout None for persistence
        self.clear_items()  # Clear any previously added items
        self.add_item(TeamDropdown())

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
        await interaction.response.send_modal(ScrimModal())  # Open the modal immediately

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

# Preview Embed

def generate_preview_embed(user_id):
    data = scrim_data[user_id]
    date_time_str = f"{data['date']} {data['time']}"
    date_time_obj = datetime.datetime.strptime(date_time_str, "%d-%m-%Y %H:%M")
    unix_timestamp = int(time.mktime(date_time_obj.timetuple()))
    players_formatted = '\n'.join(f"- {player}" for player in data['players'].split())

    embed = discord.Embed(title="🛡️ Scrim Scheduled", color=discord.Color.blue())
    embed.add_field(name="📅 Date", value=f"<t:{unix_timestamp}:F>", inline=False)
    embed.add_field(name="🏴 Opponent", value=data["opponent_team"], inline=False)
    embed.add_field(name="🎯 Opponent Avg. Rank", value=data["opponent_rank"], inline=False)
    embed.add_field(name="📖 Format", value=data["format"], inline=False)
    embed.add_field(name="🗺️ Maps", value=data["maps"], inline=False)
    embed.add_field(name="🌍 Server", value=data["server"], inline=False)
    embed.add_field(name="👥 Players", value=players_formatted, inline=False)
    return embed

# Confirm View
class ConfirmView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        team = scrim_data[self.user_id]["team"]
        channel_id = TEAM_CHANNELS.get(team)
        role_id = TEAM_ROLES.get(team)
        channel = bot.get_channel(channel_id)
        await channel.send(f"<@&{role_id}>", embed=generate_preview_embed(self.user_id))
        scheduled_scrims.append((self.user_id, scrim_data[self.user_id]))
        await interaction.response.send_message("Scrim announcement sent and scheduled for reminder!", ephemeral=True)
        scrim_data.pop(self.user_id, None)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        scrim_data.pop(self.user_id, None)
        await interaction.response.send_message("Scrim announcement canceled.", ephemeral=True)

    @discord.ui.button(label="🛠️ Edit", style=discord.ButtonStyle.primary)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ScrimModal())

# Slash Command to Start
@bot.tree.command(name="scrim", description="Start a scrim announcement!")
async def scrim(interaction: discord.Interaction):
    if not any(role.id in ALLOWED_ROLES for role in interaction.user.roles):
        embed = discord.Embed(title="❌ Access Denied", description="You do not have permission to schedule scrims.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.send_message("Use the panel below to schedule a scrim!", view=PersistentPanel(), ephemeral=True)

# Ready Event
@bot.event
async def on_ready():
    await bot.tree.sync()
    reminder_task.start()
    print(f"Logged in as {bot.user}")

    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if not channel:
        print("Panel channel not found!")
        return

    global PANEL_MESSAGE_ID

    # Try to edit the existing panel if ID exists
    if PANEL_MESSAGE_ID:
        try:
            message = await channel.fetch_message(PANEL_MESSAGE_ID)
            await message.edit(content="➕ **Schedule a Scrim**", view=PersistentPanel())
            print("Updated existing panel message!")
            return
        except (discord.NotFound, discord.HTTPException):
            print("Previous panel message not found or could not edit. Sending new panel.")

    # If no existing panel or failed fetch, send new one
    message = await channel.send("➕ **Schedule a Scrim**", view=PersistentPanel())
    PANEL_MESSAGE_ID = message.id
    print("New panel message sent!")

# Reminder Task
@tasks.loop(minutes=1)
async def reminder_task():
    now = datetime.datetime.utcnow()
    for user_id, data in scheduled_scrims.copy():
        date_time_str = f"{data['date']} {data['time']}"
        scrim_time = datetime.datetime.strptime(date_time_str, "%d-%m-%Y %H:%M")
        scrim_time = scrim_time - datetime.timedelta(minutes=0)
        if scrim_time - now <= datetime.timedelta(minutes=30) and scrim_time - now > datetime.timedelta(minutes=29):
            team = data["team"]
            channel_id = TEAM_CHANNELS.get(team)
            channel = bot.get_channel(channel_id)
            await channel.send(f"⏰ Reminder: Scrim vs {data['opponent_team']} in 30 minutes!")

# --- Run Bot ---
bot.run(os.getenv("DISCORD_TOKEN"))
