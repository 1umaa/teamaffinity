import discord
from discord.ext import commands
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
    1354079569740824650,    # Board Member Role ID
    1354078173553365132,    # Manager role ID
    1354084742072373372,    # Team Captain Role ID
    1354280624625815773     # Coach role ID
]

# Temporary storage (in real projects you'd use a DB)
scrim_data = {}

# Command to Start the Scrim Scheduling
@bot.tree.command(name="scrim", description="Start a scrim announcement!")
async def scrim(interaction: discord.Interaction):
    if not any(role.id in ALLOWED_ROLES for role in interaction.user.roles):
        embed = discord.Embed(title="❌ Access Denied", description="You do not have permission to schedule scrims.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Prompt for Team Selection
    await interaction.response.send_message("Please select your team:", view=TeamSelectionPanel(), ephemeral=True)

# Team Selection Panel with Buttons
class TeamSelectionPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Affinity EMEA 🇪🇺", style=discord.ButtonStyle.primary)
    async def select_emea(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_team(interaction, "Affinity EMEA 🇪🇺")

    @discord.ui.button(label="Affinity Academy 🇪🇺", style=discord.ButtonStyle.primary)
    async def select_academy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_team(interaction, "Affinity Academy 🇪🇺")

    @discord.ui.button(label="Affinity Auras 🇪🇺", style=discord.ButtonStyle.primary)
    async def select_auras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_team(interaction, "Affinity Auras 🇪🇺")

    @discord.ui.button(label="Affinity NA 🇺🇸", style=discord.ButtonStyle.primary)
    async def select_na(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_team(interaction, "Affinity NA 🇺🇸")

    async def select_team(self, interaction: discord.Interaction, team: str):
        user_id = interaction.user.id
        scrim_data[user_id] = {"team": team}
        
        # After selecting the team, prompt for scrim date
        await interaction.response.send_message("You selected: " + team + "\nNow, please enter the scrim date (DD-MM-YYYY):", ephemeral=True)

        # Wait for the date response
        date_msg = await bot.wait_for('message', check=lambda m: m.author == interaction.user)
        scrim_data[user_id]["date"] = date_msg.content.strip()

        # Continue prompting for other details in sequence
        await interaction.followup.send("Now, please enter the scrim time (HH:MM 24h format):", ephemeral=True)
        time_msg = await bot.wait_for('message', check=lambda m: m.author == interaction.user)
        scrim_data[user_id]["time"] = time_msg.content.strip()

        await interaction.followup.send("Please enter the opponent team name:", ephemeral=True)
        opponent_msg = await bot.wait_for('message', check=lambda m: m.author == interaction.user)
        scrim_data[user_id]["opponent_team"] = opponent_msg.content.strip()

        await interaction.followup.send("What is the opponent's average rank?", ephemeral=True)
        rank_msg = await bot.wait_for('message', check=lambda m: m.author == interaction.user)
        scrim_data[user_id]["opponent_rank"] = rank_msg.content.strip()

        await interaction.followup.send("Please provide the format (e.g., Best of 3):", ephemeral=True)
        format_msg = await bot.wait_for('message', check=lambda m: m.author == interaction.user)
        scrim_data[user_id]["format"] = format_msg.content.strip()

        await interaction.followup.send("What maps will be played?", ephemeral=True)
        maps_msg = await bot.wait_for('message', check=lambda m: m.author == interaction.user)
        scrim_data[user_id]["maps"] = maps_msg.content.strip()

        await interaction.followup.send("Please enter the server (e.g., Texas 1):", ephemeral=True)
        server_msg = await bot.wait_for('message', check=lambda m: m.author == interaction.user)
        scrim_data[user_id]["server"] = server_msg.content.strip()

        await interaction.followup.send("Please list the players (e.g., @Player1 @Player2):", ephemeral=True)
        players_msg = await bot.wait_for('message', check=lambda m: m.author == interaction.user)
        scrim_data[user_id]["players"] = players_msg.content.strip()

        # Confirm the scrim details
        await interaction.followup.send(embed=generate_preview_embed(user_id), ephemeral=True)

        # Confirmation
        await interaction.followup.send("Scrim announcement confirmed and sent!", ephemeral=True)

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

# Ready Event
@bot.event
async def on_ready():
    await bot.tree.sync()  # Sync all slash commands with Discord
    print(f"Logged in as {bot.user}")

# --- Run Bot ---
bot.run(os.getenv("DISCORD_TOKEN"))
