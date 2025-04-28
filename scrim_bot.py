import discord
from discord.ext import commands
import datetime
import os

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

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


def generate_preview_embed(user_id):
    data = scrim_data[user_id]
    date_time_str = f"{data['date']} {data['time']}"
    date_time_obj = datetime.datetime.strptime(date_time_str, "%d-%m-%Y %H:%M")
    unix_timestamp = int(date_time_obj.timestamp())
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
        await interaction.response.send_message("Scrim announcement sent!", ephemeral=True)
        scrim_data.pop(self.user_id, None)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        scrim_data.pop(self.user_id, None)
        await interaction.response.send_message("Scrim announcement canceled.", ephemeral=True)


# Slash Command to Start
@bot.tree.command(name="scrim", description="Start a scrim announcement!")
async def scrim(interaction: discord.Interaction):
    if not any(role.id in ALLOWED_ROLES for role in interaction.user.roles):
        embed = discord.Embed(title="❌ Access Denied", description="You do not have permission to schedule scrims.",
                              color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.send_message("Use the panel below to schedule a scrim!", view=PersistentPanel(),
                                            ephemeral=True)


# Persistent Panel View
class PersistentPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.clear_items()  # Reset view
        self.add_item(TeamDropdown())  # Add dropdown menu for team selection


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


# Ready Event
@bot.event
async def on_ready():
    await bot.tree.sync()  # Sync all slash commands with Discord
    print(f"Logged in as {bot.user}")


# --- Run Bot ---
bot.run(os.getenv("DISCORD_TOKEN"))
