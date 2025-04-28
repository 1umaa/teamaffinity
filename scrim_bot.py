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

# Channel ID where the persistent button message will be posted
# Change this to the channel where you want the button to appear
BUTTON_CHANNEL_ID = 1366433672093237310  # Example: using EMEA channel ID


# New function to schedule a reminder task
async def schedule_reminder(team: str, opponent_team: str, date_time_obj: datetime.datetime,
                            channel_id: int, role_id: int, players: List[str]):
    """
    Schedule a reminder 30 minutes before a scrim starts.

    Args:
        team: The team name (e.g., "Affinity EMEA")
        opponent_team: The opposing team name
        date_time_obj: The datetime object for when the scrim starts
        channel_id: The channel ID where to send the reminder
        role_id: The role ID to ping with the reminder
        players: List of player mentions
    """
    # Calculate reminder time (30 minutes before scrim)
    reminder_time = date_time_obj - datetime.timedelta(minutes=30)

    # Calculate seconds to wait until reminder should be sent
    now = datetime.datetime.now()
    seconds_until_reminder = (reminder_time - now).total_seconds()

    # Only schedule if the reminder time is in the future
    if seconds_until_reminder <= 0:
        print(f"Not scheduling reminder for {team} vs {opponent_team} as the reminder time has already passed")
        return

    # Create a unique ID for this scrim reminder
    scrim_id = f"{team}-{opponent_team}-{date_time_obj.timestamp()}"

    # Cancel any existing reminder with the same ID
    if scrim_id in scheduled_reminders and not scheduled_reminders[scrim_id].done():
        scheduled_reminders[scrim_id].cancel()

    # Schedule the reminder task
    task = asyncio.create_task(
        send_reminder_after_delay(seconds_until_reminder, team, opponent_team,
                                  date_time_obj, channel_id, role_id, players)
    )

    # Store the task reference
    scheduled_reminders[scrim_id] = task

    print(f"✅ Scheduled reminder for {team} vs {opponent_team} at {reminder_time}")


async def send_reminder_after_delay(delay_seconds: float, team: str, opponent_team: str,
                                    date_time_obj: datetime.datetime, channel_id: int,
                                    role_id: int, players: List[str]):
    """
    Wait for the specified delay and then send a reminder message.

    Args:
        delay_seconds: Seconds to wait before sending the reminder
        team: The team name
        opponent_team: The opposing team name
        date_time_obj: The datetime object for when the scrim starts
        channel_id: The channel ID where to send the reminder
        role_id: The role ID to ping with the reminder
        players: List of player mentions
    """
    try:
        # Wait until it's time to send the reminder
        await asyncio.sleep(delay_seconds)

        # Get the channel
        channel = bot.get_channel(channel_id)
        if not channel:
            print(f"Error: Could not find channel with ID {channel_id} for reminder")
            return

        # Format the start time for the reminder
        start_time = date_time_obj.strftime('%H:%M')

        # Create player pings if any are specified
        player_pings = "\n".join(players) if players else "Team members"

        # Create the reminder message with role ping
        reminder_message = (
            f"🔔 **REMINDER** 🔔\n"
            f"<@&{role_id}>\n\n"
            f"Your scrim against **{opponent_team}** starts in 30 minutes at **{start_time}**!\n\n"
            f"**Players:**\n{player_pings}\n\n"
            f"Please be ready and in voice channels."
        )

        # Get the team color for the embed
        color = TEAM_COLORS.get(team, discord.Color(0x3498DB))

        # Create an embed for the reminder
        embed = discord.Embed(
            title=f"⏰ {team} Scrim Reminder",
            description=reminder_message,
            color=color
        )

        # Send the reminder
        await channel.send(content=f"<@&{role_id}> **30-MINUTE SCRIM REMINDER**", embed=embed)
        print(f"Sent reminder for {team} vs {opponent_team}")

    except asyncio.CancelledError:
        # Handle if the task is cancelled
        print(f"Reminder for {team} vs {opponent_team} was cancelled")
    except Exception as e:
        print(f"Error sending reminder: {e}")


# Function to start the scrim workflow (used by both slash command and persistent button)
async def start_scrim_workflow(interaction: discord.Interaction):
    # Check for permissions
    if not any(role.id in ALLOWED_ROLES for role in interaction.user.roles):
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You do not have permission to schedule scrims.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Initialize user data
    user_id = interaction.user.id
    scrim_data[user_id] = {}

    # Prompt for Team Selection
    view = TeamSelectionView(user_id)
    await interaction.response.send_message(
        "Please select your team:",
        view=view,
        ephemeral=True
    )


# Command to Start the Scrim Scheduling (Slash Command)
@bot.tree.command(name="scrim", description="Start a scrim announcement!")
async def scrim(interaction: discord.Interaction):
    await start_scrim_workflow(interaction)


# Persistent Button View
class PersistentScrimButton(discord.ui.View):
    def __init__(self):
        # Set timeout to None to make it persistent
        super().__init__(timeout=None)

    # Define button with a custom_id so it persists across bot restarts
    @discord.ui.button(
        label="Schedule a Scrim",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_scrim_button",
        emoji="🗓️"
    )
    async def scrim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_scrim_workflow(interaction)


# Command to create the persistent button message
@bot.tree.command(name="create_scrim_button", description="Create a persistent scrim scheduling button")
async def create_scrim_button(interaction: discord.Interaction):
    # Check for admin permissions
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You need administrator permissions to create a persistent button.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Create embed for the button message
    embed = discord.Embed(
        title="📆 Schedule a Scrim",
        description="Click the button below to start scheduling a scrim for your team.",
        color=discord.Color.blue()
    )

    # Add information about who can use the button
    embed.add_field(
        name="Permissions",
        value="This button can be used by Team Captains, Coaches, Managers, and Board Members.",
        inline=False
    )

    # Create and send the persistent button
    view = PersistentScrimButton()
    await interaction.channel.send(embed=embed, view=view)

    # Confirm to the admin that the button was created
    await interaction.response.send_message("✅ Persistent scrim button created successfully!", ephemeral=True)


# Team Selection View with Buttons
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

        # After team selection, show the date/time modal
        await interaction.response.send_modal(ScrimDateTimeModal(self.user_id))

    async def on_timeout(self):
        # Clean up on timeout
        if self.user_id in scrim_data:
            del scrim_data[self.user_id]


# Date and Time Modal
class ScrimDateTimeModal(discord.ui.Modal, title="Scrim Date and Time"):
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

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
        # Validate date and time format
        try:
            date_str = self.date_input.value
            time_str = self.time_input.value
            date_time_str = f"{date_str} {time_str}"
            date_time_obj = datetime.datetime.strptime(date_time_str, "%d-%m-%Y %H:%M")

            # Store in scrim data
            scrim_data[self.user_id]["date"] = date_str
            scrim_data[self.user_id]["time"] = time_str
            scrim_data[self.user_id][
                "date_time_obj"] = date_time_obj  # Store the datetime object for reminder scheduling

            # Continue to opponent details
            await interaction.response.send_message(
                "Now, let's get details about the opponent:",
                view=OpponentDetailsView(self.user_id),
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid date or time format. Please use DD-MM-YYYY for date and HH:MM for time.",
                ephemeral=True
            )


# Opponent Details View
class OpponentDetailsView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="Enter Opponent Details", style=discord.ButtonStyle.primary)
    async def opponent_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(OpponentDetailsModal(self.user_id))

    async def on_timeout(self):
        if self.user_id in scrim_data:
            del scrim_data[self.user_id]


# Opponent Details Modal
class OpponentDetailsModal(discord.ui.Modal, title="Opponent Details"):
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

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
        # Store opponent details
        scrim_data[self.user_id]["opponent_team"] = self.opponent_team.value
        scrim_data[self.user_id]["opponent_rank"] = self.opponent_rank.value

        # Continue to format selection
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

        # Add format selector
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
        # Store format selection
        selected_format = self.values[0]
        scrim_data[self.user_id]["format"] = selected_format

        # Continue to maps selection
        await interaction.response.send_message(
            "Please select the maps to be played:",
            view=MapSelectionView(self.user_id),
            ephemeral=True
        )


# Maps Selection View
class MapSelectionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

        # Add maps selector
        max_maps = 5  # Allow up to 5 maps to be selected
        self.add_item(MapSelector(user_id, max_maps))

    async def on_timeout(self):
        if self.user_id in scrim_data:
            del scrim_data[self.user_id]


# Maps Selector Dropdown
class MapSelector(discord.ui.Select):
    def __init__(self, user_id: int, max_maps: int):
        self.user_id = user_id

        options = [
            discord.SelectOption(label=map_name, value=map_name)
            for map_name in MAP_OPTIONS
        ]

        super().__init__(
            placeholder="Select maps...",
            min_values=1,
            max_values=max_maps,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # Store maps selection
        selected_maps = self.values
        scrim_data[self.user_id]["maps"] = selected_maps

        # Continue to server selection
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

        # Add server selector
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
        # Store server selection
        selected_server = self.values[0]
        scrim_data[self.user_id]["server"] = selected_server

        # Continue to player selection
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
        # Process player input - split by newlines for proper handling
        players = self.players_input.value.strip().split('\n')
        scrim_data[self.user_id]["players"] = players

        # Show preview and confirmation
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
        # Send the announcement to the appropriate channel
        await send_scrim_announcement(self.user_id, interaction)

        await interaction.response.send_message(
            "✅ Scrim announcement confirmed and sent! A reminder will be sent 30 minutes before the scrim starts.",
            ephemeral=True
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Clean up data
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

    # Format date and time
    date_time_str = f"{data['date']} {data['time']}"
    try:
        date_time_obj = datetime.datetime.strptime(date_time_str, "%d-%m-%Y %H:%M")
        unix_timestamp = int(date_time_obj.timestamp())
    except ValueError:
        # Fallback in case of format issues
        unix_timestamp = int(datetime.datetime.now().timestamp())

    # Format players list
    players_formatted = '\n'.join(f"- {player}" for player in data['players'])

    # Format maps list if it's a list
    maps_value = data.get("maps", [])
    if isinstance(maps_value, list):
        maps_text = '\n'.join(f"- {map_name}" for map_name in maps_value)
    else:
        maps_text = str(maps_value)

    # Get the team color from the TEAM_COLORS dictionary
    color = TEAM_COLORS.get(team, discord.Color(0x3498DB))  # Default to a nice blue if team not found

    # Create embed with team-specific color
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

    # Add reminder note
    embed.add_field(name="⏰ Reminder", value="A reminder will be sent 30 minutes before the scrim starts.",
                    inline=False)

    return embed


# Send scrim announcement to the proper channel
async def send_scrim_announcement(user_id: int, interaction: discord.Interaction) -> None:
    data = scrim_data[user_id]
    team = data["team"]

    # Get channel and role IDs
    channel_id = TEAM_CHANNELS.get(team)
    role_id = TEAM_ROLES.get(team)

    if not channel_id:
        await interaction.followup.send(
            f"❌ Error: Could not find channel for team {team}",
            ephemeral=True
        )
        return

    # Generate embed
    embed = generate_preview_embed(user_id)

    # Get the channel
    channel = bot.get_channel(channel_id)
    if not channel:
        await interaction.followup.send(
            f"❌ Error: Could not find channel with ID {channel_id}",
            ephemeral=True
        )
        return

    # Include role ping in the message content
    content = (f"# <@&{role_id}> Scrim scheduled! "
               f"Please review the below and reach out to your Team Captain if you won't be available, so that we can find a substitute")

    # Send the announcement
    await channel.send(content=content, embed=embed)

    # Schedule the reminder for 30 minutes before the scrim starts
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

    # Clean up user data
    del scrim_data[user_id]


# Ready Event
@bot.event
async def on_ready():
    try:
        # Sync all slash commands with Discord
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
        print(f"Logged in as {bot.user}")

        # Setup the persistent view when the bot starts
        # This allows the button to work even after bot restarts
        bot.add_view(PersistentScrimButton())
        print("Added persistent button view")

        # Optional: You can make the bot automatically post the button when it starts
        # Uncomment the following code to enable this feature:
        """
        channel = bot.get_channel(BUTTON_CHANNEL_ID)
        if channel:
            # Check if the button already exists
            # This is a naive implementation - you might want to store message IDs
            # in a database to check more accurately
            messages = [message async for message in channel.history(limit=20)]
            button_exists = any("📆 Schedule a Scrim" in message.content for message in messages)

            if not button_exists:
                embed = discord.Embed(
                    title="📆 Schedule a Scrim",
                    description="Click the button below to start scheduling a scrim for your team.",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="Permissions",
                    value="This button can be used by Team Captains, Coaches, Managers, and Board Members.",
                    inline=False
                )
                await channel.send(embed=embed, view=PersistentScrimButton())
                print("Created persistent button message")
        """

    except Exception as e:
        print(f"Error during startup: {e}")


# --- Run Bot ---
bot.run(os.getenv("DISCORD_TOKEN"))
