import discord
from discord.ext import commands
import datetime
import os
import asyncio
from discord import app_commands
from typing import Dict, List, Optional, Union, Any
import re
import googleapiclient.discovery
from google.oauth2.credentials import Credentials
import logging
import sqlite3
import aiosqlite

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log")
    ]
)
logger = logging.getLogger("affinity_bot")

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# --- Configuration Constants ---
# Team configuration
TEAM_CONFIG = {
    "Affinity EMEA": {
        "channel_id": 1354698542173786344,
        "role_id": 1354084830140436611,
        "color": discord.Color(0x12d6df),  # #12d6df - EMEA Blue
    },
    "Affinity ACAD EMEA": {
        "channel_id": 1366431756164665496,
        "role_id": 1354085016778575934,
        "color": discord.Color(0xf70fff),  # #f70fff - ACAD Purple
    },
    "Affinity Auras": {
        "channel_id": 1366432079440515154,
        "role_id": 1354085121166278708,
        "color": discord.Color(0xff8cfb),  # #ff8cfb - Auras Pink
    },
    "Affinity NA": {
        "channel_id": 1354508442135560323,
        "role_id": 1354085225600385044,
        "color": discord.Color(0xcb0000),  # #cb0000 - NA Red
    },
    "Affinity ACAD NA": {
        "channel_id": 1393908768802340906,
        "role_id": 1393906573029408798,
        "color": discord.Color(0xcaa422)  # #caa422 - ACAD Orange
    },
}

# Role IDs that are allowed to schedule scrims
ALLOWED_ROLES = [
    1354079569740824650,  # Board Member Role ID
    1354078173553365132,  # Manager role ID
    1354084742072373372,  # Team Captain Role ID
    1354280624625815773   # Coach role ID
]

# Channel for absence notifications
ABSENCE_MANAGEMENT_CHANNEL_ID = 1367628087130456135

# Management role ID for absence notifications
MANAGEMENT_ROLE_ID = 1354078173553365132  # Using the Manager role ID

# Maps, servers, and format options
MAP_OPTIONS = ["Abyss", "Ascent", "Bind", "Breeze", "Corrode", "Fracture", "Haven", "Icebox", "Lotus", "Pearl", "Split", "Sunset"]
SERVER_OPTIONS = ["Frankfurt", "London", "Amsterdam", "Paris", "Warsaw", "Stockholm", "Madrid", "Virginia", "Illinois", "Texas", "Oregon", "California"]
FORMAT_OPTIONS = ["1 Game", "2 Games", "1 Game MR24", "2 Games MR24", "Best of 1", "Best of 3", "Best of 5"]

# Absence types with their descriptions
ABSENCE_TYPES = [
    {"label": "Vacation", "value": "vacation", "description": "Planned time off"},
    {"label": "Sick Leave", "value": "sick", "description": "Unable to attend due to illness"},
    {"label": "Personal Day", "value": "personal", "description": "Time off for personal matters"},
    {"label": "Family Emergency", "value": "family", "description": "Absence due to family emergency"},
    {"label": "Other", "value": "other", "description": "Other type of absence"}
]

# Google Calendar color mapping
GCAL_COLOR_MAP = {
    "Vacation": "9",      # Blue
    "Sick Leave": "11",   # Red
    "Personal Day": "5",  # Yellow
    "Family Emergency": "4",  # Purple
    "Other": "8",         # Gray
}

# Timezone mapping for common timezone strings
TIMEZONE_MAPPING = {
    "UTC": 0, "GMT": 0,
    "CET": 1, "CEST": 2, "BST": 1,
    "EST": -4, "EDT": -4, "PST": -8, "PDT": -7
}

# --- Database Setup ---
class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path="bot_data.db"):
        self.db_path = db_path
        self.connection = None
        
    async def initialize(self):
        """Initialize the database and create tables if they don't exist"""
        self.connection = await aiosqlite.connect(self.db_path)
        
        # Create scrim table
        await self.connection.execute('''
        CREATE TABLE IF NOT EXISTS scrims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team TEXT NOT NULL,
            opponent TEXT NOT NULL,
            start_time TIMESTAMP NOT NULL,
            format TEXT NOT NULL,
            maps TEXT NOT NULL,
            server TEXT NOT NULL,
            players TEXT NOT NULL,
            opponent_rank TEXT NOT NULL,
            reminder_sent BOOLEAN DEFAULT FALSE,
            channel_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL
        )
        ''')
        
        # Create absence table
        await self.connection.execute('''
        CREATE TABLE IF NOT EXISTS absences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            absence_type TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            team TEXT NOT NULL,
            reason TEXT NOT NULL,
            calendar_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        await self.connection.commit()
        logger.info("Database initialized")
        
    async def close(self):
        """Close the database connection"""
        if self.connection:
            await self.connection.close()
            
    async def add_scrim(self, team, opponent, start_time, format_type, maps, server, 
                        players, opponent_rank, channel_id, role_id):
        """Add a scrim to the database"""
        # Convert maps list to comma-separated string if it's a list
        if isinstance(maps, list):
            maps = ",".join(maps)
            
        # Convert players list to comma-separated string if it's a list
        if isinstance(players, list):
            players = ",".join(players)
            
        await self.connection.execute('''
        INSERT INTO scrims 
        (team, opponent, start_time, format, maps, server, players, opponent_rank, channel_id, role_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (team, opponent, start_time.timestamp(), format_type, maps, server, 
              players, opponent_rank, channel_id, role_id))
        
        await self.connection.commit()
        
        # Get the last inserted ID
        cursor = await self.connection.execute('SELECT last_insert_rowid()')
        row = await cursor.fetchone()
        return row[0] if row else None
        
    async def get_upcoming_scrims(self, hours_ahead=24):
        """Get scrims in the next X hours that need reminders"""
        now = datetime.datetime.now().timestamp()
        upcoming_time = (datetime.datetime.now() + datetime.timedelta(hours=hours_ahead)).timestamp()
        
        cursor = await self.connection.execute('''
        SELECT id, team, opponent, start_time, format, maps, server, players, 
               opponent_rank, channel_id, role_id 
        FROM scrims 
        WHERE start_time BETWEEN ? AND ? 
        AND reminder_sent = FALSE
        ''', (now, upcoming_time))
        
        rows = await cursor.fetchall()
        results = []
        
        for row in rows:
            # Convert timestamp to datetime
            start_time = datetime.datetime.fromtimestamp(row[3])
            
            # Parse maps and players back to lists
            maps = row[5].split(",") if row[5] else []
            players = row[7].split(",") if row[7] else []
            
            results.append({
                "id": row[0],
                "team": row[1],
                "opponent": row[2],
                "start_time": start_time,
                "format": row[4],
                "maps": maps,
                "server": row[6],
                "players": players,
                "opponent_rank": row[8],
                "channel_id": row[9],
                "role_id": row[10]
            })
            
        return results
        
    async def mark_reminder_sent(self, scrim_id):
        """Mark a scrim reminder as sent"""
        await self.connection.execute('''
        UPDATE scrims SET reminder_sent = TRUE WHERE id = ?
        ''', (scrim_id,))
        await self.connection.commit()
        
    async def add_absence(self, user_id, user_name, absence_type, start_date, end_date, team, reason, calendar_link=None):
        """Add an absence record to the database"""
        await self.connection.execute('''
        INSERT INTO absences 
        (user_id, user_name, absence_type, start_date, end_date, team, reason, calendar_link)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, user_name, absence_type, start_date, end_date, team, reason, calendar_link))
        
        await self.connection.commit()
        
        # Get the last inserted ID
        cursor = await self.connection.execute('SELECT last_insert_rowid()')
        row = await cursor.fetchone()
        return row[0] if row else None

# Initialize the database manager
db_manager = DatabaseManager(db_path="/app/data/bot_data.db")

# Cached channel and role references
channel_cache = {}
role_cache = {}

# Session cache for user data during workflows
session_cache = {}

# --- Calendar Integration ---
class CalendarManager:
    """Handles Google Calendar integration"""
    
    def __init__(self):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        self.calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
        self.service = None
        
    async def initialize(self):
        """Initialize the Google Calendar service"""
        try:
            if not all([self.client_id, self.client_secret, self.refresh_token, self.calendar_id]):
                logger.warning("Google Calendar credentials not fully configured")
                return False
                
            credentials = Credentials.from_authorized_user_info({
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            })
            
            self.service = googleapiclient.discovery.build(
                "calendar", "v3", credentials=credentials
            )
            logger.info("Google Calendar service initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Google Calendar: {e}")
            return False
            
    async def add_absence(self, player_name, absence_type, start_date, end_date, reason, team):
        """Add an absence to Google Calendar"""
        if not self.service:
            logger.warning("Google Calendar service not initialized")
            return None
            
        try:
            # Get color ID based on absence type
            color_id = GCAL_COLOR_MAP.get(absence_type, "1")
            
            # Create event
            event = {
                "summary": f"{player_name} - {absence_type}",
                "description": f"Team: {team}\nReason: {reason}",
                "start": {
                    "date": start_date,  # All day event
                },
                "end": {
                    "date": end_date,  # All day event
                },
                "colorId": color_id,
            }
            
            # Insert the event
            response = await asyncio.to_thread(
                self.service.events().insert(
                    calendarId=self.calendar_id,
                    body=event
                ).execute
            )
            
            logger.info(f"Calendar event created: {response.get('htmlLink')}")
            return response.get("htmlLink")
        except Exception as e:
            logger.error(f"Error adding to Google Calendar: {e}")
            return None

# Initialize the calendar manager
calendar_manager = CalendarManager()

# --- Helper Functions ---
def is_valid_date(date_string: str) -> bool:
    """Validate if the string is a correctly formatted date (DD/MM/YYYY)."""
    # Check format with regex for DD/MM/YYYY
    if not re.match(r"^\d{2}/\d{2}/\d{4}$", date_string):
        return False

    # Check if it's a valid date
    try:
        datetime.datetime.strptime(date_string, "%d/%m/%Y")
        return True
    except ValueError:
        return False

def convert_date_format(date_string: str, from_format="%d/%m/%Y", to_format="%Y-%m-%d") -> str:
    """Convert date format."""
    try:
        date_obj = datetime.datetime.strptime(date_string, from_format)
        return date_obj.strftime(to_format)
    except ValueError as e:
        logger.error(f"Date conversion error: {e}")
        return date_string

def get_timezone_offset(timezone_str: str) -> int:
    """Get timezone offset in hours from timezone string."""
    # Handle common timezone strings
    if timezone_str in TIMEZONE_MAPPING:
        return TIMEZONE_MAPPING[timezone_str]
        
    # Handle UTC+/- format
    if "UTC+" in timezone_str:
        return int(timezone_str.replace("UTC+", ""))
    elif "UTC-" in timezone_str:
        return -int(timezone_str.replace("UTC-", ""))
    elif "GMT+" in timezone_str:
        return int(timezone_str.replace("GMT+", ""))
    elif "GMT-" in timezone_str:
        return -int(timezone_str.replace("GMT-", ""))
        
    return 0  # Default to UTC

def has_permission(member: discord.Member) -> bool:
    """Check if a member has permission to use admin commands."""
    return any(role.id in ALLOWED_ROLES for role in member.roles) or member.guild_permissions.administrator

def generate_scrim_embed(team: str, data: Dict[str, Any]) -> discord.Embed:
    """Generate embed for scrim announcement."""
    # Get the team color
    color = TEAM_CONFIG.get(team, {}).get("color", discord.Color(0x3498DB))
    
    # Format players list
    players = data.get('players', [])
    if isinstance(players, str):
        players = players.split(',')
    players_formatted = '\n'.join(f"- {player}" for player in players)
    
    # Format maps list
    maps_value = data.get("maps", [])
    if isinstance(maps_value, str):
        maps_value = maps_value.split(',')
    maps_text = '\n'.join(f"- {map_name}" for map_name in maps_value)
    
    # Get unix timestamp for Discord time format
    start_time = data.get("start_time")
    if isinstance(start_time, datetime.datetime):
        unix_timestamp = int(start_time.timestamp())
    else:
        unix_timestamp = int(start_time)
    
    # Create embed
    embed = discord.Embed(
        title=f"🛡️ {team} Scrim Scheduled",
        color=color
    )
    
    embed.add_field(name="📅 Date & Time", value=f"<t:{unix_timestamp}:F>", inline=False)
    embed.add_field(name="🏴 Opponent", value=data.get("opponent", "TBD"), inline=False)
    embed.add_field(name="🎯 Opponent Rank", value=data.get("opponent_rank", "Unknown"), inline=False)
    embed.add_field(name="📖 Format", value=data.get("format", "TBD"), inline=False)
    embed.add_field(name="🗺️ Maps", value=maps_text, inline=False)
    embed.add_field(name="🌍 Server", value=data.get("server", "TBD"), inline=False)
    embed.add_field(name="👥 Players", value=players_formatted, inline=False)
    
    # Add reminder note
    embed.add_field(name="⏰ Reminder", value="A reminder will be sent 30 minutes before the scrim starts.",
                    inline=False)
                    
    return embed

# --- UI Components with Improved Reusability ---
class SelectionDropdown(discord.ui.Select):
    """Generic dropdown for selections."""
    
    def __init__(self, options, placeholder, min_values=1, max_values=1, custom_id=None):
        """Initialize dropdown with options."""
        select_options = [
            discord.SelectOption(label=option, value=option)
            for option in options
        ]
        
        super().__init__(
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            options=select_options,
            custom_id=custom_id
        )

class BasicView(discord.ui.View):
    """Base view with common functionality."""
    
    def __init__(self, user_id: int, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        
    async def on_timeout(self):
        """Clean up on timeout."""
        if self.user_id in session_cache:
            del session_cache[self.user_id]
            logger.info(f"Session timed out for user {self.user_id}")

class ConfirmCancelView(BasicView):
    """View with confirm and cancel buttons."""
    
    def __init__(self, user_id: int, confirm_label="Confirm", cancel_label="Cancel", timeout=300):
        super().__init__(user_id, timeout)
        
        # Add confirm button
        confirm_button = discord.ui.Button(
            label=confirm_label, 
            style=discord.ButtonStyle.success,
            custom_id=f"confirm_{user_id}"
        )
        confirm_button.callback = self.confirm_callback
        self.add_item(confirm_button)
        
        # Add cancel button
        cancel_button = discord.ui.Button(
            label=cancel_label, 
            style=discord.ButtonStyle.danger,
            custom_id=f"cancel_{user_id}"
        )
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)
        
    async def confirm_callback(self, interaction: discord.Interaction):
        """Called when confirm is pressed. Override in subclasses."""
        pass
        
    async def cancel_callback(self, interaction: discord.Interaction):
        """Called when cancel is pressed."""
        if self.user_id in session_cache:
            del session_cache[self.user_id]
        
        await interaction.response.send_message(
            "❌ Operation cancelled.",
            ephemeral=True
        )

# --- Absence Management Components ---
class AbsenceButton(discord.ui.Button):
    """Button for submitting an absence notification."""

    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Submit Absence",
            custom_id="submit_absence",
            emoji="📅"
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle button press."""
        # Initialize session data
        user_id = interaction.user.id
        session_cache[user_id] = {"workflow": "absence"}
        
        # Create dropdown for absence type
        select = discord.ui.Select(
            placeholder="Select absence type",
            options=[
                discord.SelectOption(
                    label=absence_type["label"],
                    value=absence_type["value"],
                    description=absence_type["description"]
                )
                for absence_type in ABSENCE_TYPES
            ],
            min_values=1,
            max_values=1
        )
        
        # Create the view and add the dropdown
        view = discord.ui.View(timeout=300)
        select.callback = lambda i: self.on_absence_type_select(i, select)
        view.add_item(select)
        
        await interaction.response.send_message(
            "Please select the type of absence:",
            view=view,
            ephemeral=True
        )
        
    async def on_absence_type_select(self, interaction: discord.Interaction, select):
        """Handle absence type selection."""
        user_id = interaction.user.id
        absence_type = next(
            (type for type in ABSENCE_TYPES if type["value"] == select.values[0]),
            None
        )
        
        if absence_type:
            session_cache[user_id]["absence_type"] = absence_type
            
            # Show the modal form
            modal = AbsenceDetailsModal(user_id, absence_type)
            await interaction.response.send_modal(modal)

class PersistentAbsenceView(discord.ui.View):
    """View containing the persistent absence button."""

    def __init__(self):
        super().__init__(timeout=None)  # Persistent view has no timeout
        self.add_item(AbsenceButton())

class AbsenceDetailsModal(discord.ui.Modal):
    """Modal form for collecting absence details."""

    def __init__(self, user_id: int, absence_type: Dict[str, str]):
        self.user_id = user_id
        self.absence_type = absence_type
        super().__init__(title=f"{absence_type['label']} Details")

        # Create the form fields with updated format
        self.start_date = discord.ui.TextInput(
            label="Start Date (DD/MM/YYYY)",
            placeholder="e.g., 10/05/2025",
            required=True
        )
        
        self.end_date = discord.ui.TextInput(
            label="End Date (DD/MM/YYYY)",
            placeholder="e.g., 15/05/2025",
            required=True
        )
        
        self.team = discord.ui.TextInput(
            label="Your Team",
            placeholder="e.g., Affinity EMEA",
            required=True
        )
        
        self.reason = discord.ui.TextInput(
            label="Reason for absence",
            placeholder="Please provide details about your absence...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )

        # Add the inputs to the modal
        self.add_item(self.start_date)
        self.add_item(self.end_date)
        self.add_item(self.team)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        """Process the form submission."""
        try:
            # Get the form data
            start_date = self.start_date.value
            end_date = self.end_date.value
            team = self.team.value
            reason = self.reason.value
            user = interaction.user

            # Validate dates
            if not is_valid_date(start_date) or not is_valid_date(end_date):
                await interaction.response.send_message(
                    "Invalid date format. Please use DD/MM/YYYY.",
                    ephemeral=True
                )
                return

            # Check if the team exists
            if team not in TEAM_CONFIG:
                await interaction.response.send_message(
                    f"Team '{team}' not found. Available teams: {', '.join(TEAM_CONFIG.keys())}",
                    ephemeral=True
                )
                return

            # First, acknowledge the submission
            await interaction.response.send_message(
                "Processing your absence submission...",
                ephemeral=True
            )

            # Convert dates for Google Calendar
            calendar_start_date = convert_date_format(start_date)
            calendar_end_date = convert_date_format(end_date)

            # Add to Google Calendar
            calendar_link = None
            try:
                calendar_link = await calendar_manager.add_absence(
                    player_name=user.display_name,
                    absence_type=self.absence_type["label"],
                    start_date=calendar_start_date,
                    end_date=calendar_end_date,
                    reason=reason,
                    team=team
                )
            except Exception as e:
                logger.error(f"Error adding to Google Calendar: {e}")

            # Add absence to database
            await db_manager.add_absence(
                user_id=user.id,
                user_name=user.display_name,
                absence_type=self.absence_type["label"],
                start_date=calendar_start_date,
                end_date=calendar_end_date,
                team=team,
                reason=reason,
                calendar_link=calendar_link
            )

            # Create confirmation embed
            confirm_embed = discord.Embed(
                title="Absence Submitted",
                color=discord.Color.green()
            )
            confirm_embed.add_field(name="Type", value=self.absence_type["label"], inline=False)
            confirm_embed.add_field(name="Start Date", value=start_date, inline=True)
            confirm_embed.add_field(name="End Date", value=end_date, inline=True)
            confirm_embed.add_field(name="Team", value=team, inline=False)
            confirm_embed.add_field(name="Reason", value=reason, inline=False)
            confirm_embed.timestamp = datetime.datetime.now()

            # Send confirmation to the user
            await interaction.followup.send(
                content="Your absence has been submitted successfully!",
                embed=confirm_embed,
                ephemeral=True
            )

            # Send notification to management channel
            await self.send_management_notification(
                interaction,
                user,
                self.absence_type["label"],
                start_date,
                end_date,
                team,
                reason,
                calendar_link
            )

            # Inform user about calendar addition (if successful)
            if calendar_link:
                await interaction.followup.send(
                    f"Event added to the team calendar: {calendar_link}",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error processing absence: {e}")
            await interaction.followup.send(
                "An error occurred while processing your absence request. Please try again later.",
                ephemeral=True
            )

    async def send_management_notification(
            self,
            interaction: discord.Interaction,
            user: discord.User,
            absence_type: str,
            start_date: str,
            end_date: str,
            team: str,
            reason: str,
            calendar_link: Optional[str] = None
    ):
        """Send notification to the management channel."""
        try:
            # Get the management channel
            channel = interaction.client.get_channel(ABSENCE_MANAGEMENT_CHANNEL_ID)
            if not channel:
                logger.error(f"Management channel with ID {ABSENCE_MANAGEMENT_CHANNEL_ID} not found.")
                return

            # Get team role ID
            team_role_id = TEAM_CONFIG[team]["role_id"]

            # Create notification embed
            notification_embed = discord.Embed(
                title="New Absence Notification",
                color=discord.Color.orange()
            )
            notification_embed.add_field(name="Player", value=user.mention, inline=False)
            notification_embed.add_field(name="Type", value=absence_type, inline=False)
            notification_embed.add_field(name="Start Date", value=start_date, inline=True)
            notification_embed.add_field(name="End Date", value=end_date, inline=True)
            notification_embed.add_field(name="Team", value=team, inline=False)
            notification_embed.add_field(name="Reason", value=reason, inline=False)
            
            if calendar_link:
                notification_embed.add_field(name="Calendar", value=f"[View in Calendar]({calendar_link})", inline=False)
                
            notification_embed.timestamp = datetime.datetime.now()

            # Mention the team role and management role
            content = f"<@&{team_role_id}> <@&{MANAGEMENT_ROLE_ID}> - New absence notification from team member"

            await channel.send(content=content, embed=notification_embed)
            
        except Exception as e:
            logger.error(f"Error sending management notification: {e}")

# --- Scrim Scheduler Components ---
class TeamSelectionView(BasicView):
    """View for team selection with buttons."""
    
    def __init__(self, user_id: int):
        super().__init__(user_id)
        
        # Add a button for each team
        for team_name in TEAM_CONFIG.keys():
            button = discord.ui.Button(label=team_name, style=discord.ButtonStyle.primary)
            button.callback = lambda i, tn=team_name: self.select_team(i, tn)
            self.add_item(button)
    
    async def select_team(self, interaction: discord.Interaction, team: str):
        """Handle team selection."""
        session_cache[self.user_id]["team"] = team
        
        # After team selection, show the date/time modal
        await interaction.response.send_modal(ScrimDateTimeModal(self.user_id))

class ScrimDateTimeModal(discord.ui.Modal, title="Scrim Date and Time"):
    """Modal for collecting date and time information."""
    
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

        self.date_input = discord.ui.TextInput(
            label="Date (DD/MM/YYYY)",
            placeholder="e.g., 30/04/2025",
            required=True,
            min_length=10,
            max_length=10
        )

        self.time_input = discord.ui.TextInput(
            label="Time (HH:MM 24h format)",
            placeholder="e.g., 19:30",
            required=True,
            min_length=5,
            max_length=5
        )

        self.timezone_input = discord.ui.TextInput(
            label="Your timezone (e.g. UTC, GMT, CET, EST)",
            placeholder="e.g., UTC or UTC+1",
            required=True,
            min_length=2,
            max_length=10
        )

        self.add_item(self.date_input)
        self.add_item(self.time_input)
        self.add_item(self.timezone_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Process the date and time submission."""
        try:
            # Get the input values
            date_str = self.date_input.value
            time_str = self.time_input.value
            timezone_str = self.timezone_input.value.upper().strip()

            # Validate date and time format
            date_time_str = f"{date_str} {time_str}"
            try:
                naive_date_time_obj = datetime.datetime.strptime(date_time_str, "%d/%m/%Y %H:%M")
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid date or time format. Please use DD/MM/YYYY for date and HH:MM for time.",
                    ephemeral=True
                )
                return

            # Get timezone offset
            timezone_offset = get_timezone_offset(timezone_str)

            # Calculate UTC timestamp
            utc_timestamp = int(naive_date_time_obj.timestamp()) - (timezone_offset * 3600)
            date_time_obj = datetime.datetime.fromtimestamp(utc_timestamp)

            # Store in session cache
            session_cache[self.user_id].update({
                "date": date_str,
                "time": time_str,
                "timezone": timezone_str,
                "start_time": date_time_obj
            })

            # Continue to opponent details
            await interaction.response.send_message(
                "Now, let's get details about the opponent:",
                view=OpponentDetailsView(self.user_id),
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error processing date/time: {e}")
            await interaction.response.send_message(
                "An error occurred. Please try again with a valid date, time, and timezone.",
                ephemeral=True
            )

class OpponentDetailsModal(discord.ui.Modal, title="Opponent Details"):
    """Modal for collecting opponent details."""
    
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

        self.opponent_team = discord.ui.TextInput(
            label="Opponent Team Name",
            placeholder="e.g., Team Liquid",
            required=True
        )

        self.opponent_rank = discord.ui.TextInput(
            label="Opponent's Average Rank",
            placeholder="e.g., Immortal 2",
            required=True
        )
        
        self.add_item(self.opponent_team)
        self.add_item(self.opponent_rank)

    async def on_submit(self, interaction: discord.Interaction):
        """Process the opponent details submission."""
        # Store opponent details
        session_cache[self.user_id].update({
            "opponent": self.opponent_team.value,
            "opponent_rank": self.opponent_rank.value
        })

        # Create the format selection view
        view = discord.ui.View(timeout=300)
        
        # Add format selector dropdown
        format_selector = SelectionDropdown(
            options=FORMAT_OPTIONS,
            placeholder="Select match format...",
            custom_id=f"format_select_{self.user_id}"
        )
        format_selector.callback = lambda i: self.on_format_select(i, format_selector)
        view.add_item(format_selector)
        
        # Continue to format selection
        await interaction.response.send_message(
            "Please select the match format:",
            view=view,
            ephemeral=True
        )
        
    async def on_format_select(self, interaction: discord.Interaction, select):
        """Handle format selection."""
        selected_format = select.values[0]
        session_cache[self.user_id]["format"] = selected_format
        
        # Create maps selection view
        view = discord.ui.View(timeout=300)
        
        # Add maps selector dropdown
        maps_selector = SelectionDropdown(
            options=MAP_OPTIONS,
            placeholder="Select maps...",
            min_values=1,
            max_values=5,  # Allow up to 5 maps
            custom_id=f"maps_select_{self.user_id}"
        )
        maps_selector.callback = lambda i: self.on_maps_select(i, maps_selector)
        view.add_item(maps_selector)
        
        # Continue to maps selection
        await interaction.response.send_message(
            "Please select the maps to be played:",
            view=view,
            ephemeral=True
        )
        
    async def on_maps_select(self, interaction: discord.Interaction, select):
        """Handle maps selection."""
        selected_maps = select.values
        session_cache[self.user_id]["maps"] = selected_maps
        
        # Create server selection view
        view = discord.ui.View(timeout=300)
        
        # Add server selector dropdown
        server_selector = SelectionDropdown(
            options=SERVER_OPTIONS,
            placeholder="Select server location...",
            custom_id=f"server_select_{self.user_id}"
        )
        server_selector.callback = lambda i: self.on_server_select(i, server_selector)
        view.add_item(server_selector)
        
        # Continue to server selection
        await interaction.response.send_message(
            "Please select the server:",
            view=view,
            ephemeral=True
        )
        
    async def on_server_select(self, interaction: discord.Interaction, select):
        """Handle server selection."""
        selected_server = select.values[0]
        session_cache[self.user_id]["server"] = selected_server
        
        # Continue to player selection modal
        await interaction.response.send_modal(PlayerSelectionModal(self.user_id))

class OpponentDetailsView(BasicView):
    """View for opponent details button."""
    
    def __init__(self, user_id: int):
        super().__init__(user_id)
        
        # Add button to open opponent details modal
        button = discord.ui.Button(
            label="Enter Opponent Details", 
            style=discord.ButtonStyle.primary
        )
        button.callback = self.on_button_click
        self.add_item(button)
        
    async def on_button_click(self, interaction: discord.Interaction):
        await interaction.response.send_modal(OpponentDetailsModal(self.user_id))

class PlayerSelectionModal(discord.ui.Modal, title="Player Selection"):
    """Modal for entering player information."""
    
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

        self.players_input = discord.ui.TextInput(
            label="Players (one per line)",
            style=discord.TextStyle.paragraph,
            placeholder="@Player1\n@Player2\n@Player3\n@Player4\n@Player5",
            required=True
        )
        
        self.add_item(self.players_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Process player selection."""
        # Process player input - split by newlines for proper handling
        players = self.players_input.value.strip().split('\n')
        session_cache[self.user_id]["players"] = players

        # Generate preview embed
        team = session_cache[self.user_id]["team"]
        embed = generate_scrim_embed(team, session_cache[self.user_id])

        # Create confirmation view
        view = ScrimConfirmationView(self.user_id)
        
        await interaction.response.send_message(
            "Here's a preview of your scrim announcement:",
            embed=embed,
            view=view,
            ephemeral=True
        )

class ScrimConfirmationView(ConfirmCancelView):
    """View for confirming or canceling a scrim announcement."""
    
    def __init__(self, user_id: int):
        super().__init__(
            user_id=user_id,
            confirm_label="Confirm & Send",
            cancel_label="Cancel"
        )
        
    async def confirm_callback(self, interaction: discord.Interaction):
        """Handle scrim confirmation."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get scrim data
            user_id = self.user_id
            data = session_cache[user_id]
            team = data["team"]
            
            # Get channel and role IDs
            team_config = TEAM_CONFIG.get(team, {})
            channel_id = team_config.get("channel_id")
            role_id = team_config.get("role_id")
            
            if not channel_id:
                await interaction.followup.send(
                    f"❌ Error: Could not find channel for team {team}",
                    ephemeral=True
                )
                return
                
            # Get the channel
            channel = interaction.client.get_channel(channel_id)
            if not channel:
                await interaction.followup.send(
                    f"❌ Error: Could not find channel with ID {channel_id}",
                    ephemeral=True
                )
                return
                
            # Generate embed
            embed = generate_scrim_embed(team, data)
            
            # Include role ping in the message content
            content = (
                f"# <@&{role_id}>\n"
                f"\n"
                f"Please review the below and reach out to your Team Captain if you won't be available, "
                f"so that we can find a substitute"
            )
            
            # Send the announcement
            await channel.send(content=content, embed=embed)
            
            # Add to database
            scrim_id = await db_manager.add_scrim(
                team=team,
                opponent=data["opponent"],
                start_time=data["start_time"],
                format_type=data["format"],
                maps=data["maps"],
                server=data["server"],
                players=data["players"],
                opponent_rank=data["opponent_rank"],
                channel_id=channel_id,
                role_id=role_id
            )
            
            logger.info(f"Added scrim to database with ID {scrim_id}")
            
            # Clean up session data
            del session_cache[user_id]
            
            await interaction.followup.send(
                "✅ Scrim announcement confirmed and sent! A reminder will be sent 30 minutes before the scrim starts.",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error confirming scrim: {e}")
            await interaction.followup.send(
                "An error occurred while sending the scrim announcement. Please try again.",
                ephemeral=True
            )

# Persistent button views
class PersistentScrimButton(discord.ui.View):
    """Persistent button for scheduling a scrim."""
    
    def __init__(self):
        # Set timeout to None to make it persistent
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Schedule a Scrim",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_scrim_button",
        emoji="🗓️"
    )
    async def scrim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_scrim_workflow(interaction)

# --- Commands and Workflows ---
async def start_scrim_workflow(interaction: discord.Interaction):
    """Start the scrim scheduling workflow."""
    # Check for permissions
    if not has_permission(interaction.user):
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You do not have permission to schedule scrims.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Initialize session data
    user_id = interaction.user.id
    session_cache[user_id] = {"workflow": "scrim"}

    # Prompt for Team Selection
    view = TeamSelectionView(user_id)
    await interaction.response.send_message(
        "Please select your team:",
        view=view,
        ephemeral=True
    )

@bot.tree.command(name="scrim", description="Start a scrim announcement!")
async def scrim(interaction: discord.Interaction):
    """Slash command to start scheduling a scrim."""
    await start_scrim_workflow(interaction)

@bot.tree.command(name="absence", description="Submit an absence notification")
async def absence(interaction: discord.Interaction):
    """Slash command to submit an absence."""
    # Initialize session data
    user_id = interaction.user.id
    session_cache[user_id] = {"workflow": "absence"}
    
    # Create and show absence type selection view
    view = discord.ui.View(timeout=300)
    select = discord.ui.Select(
        placeholder="Select absence type",
        options=[
            discord.SelectOption(
                label=absence_type["label"],
                value=absence_type["value"],
                description=absence_type["description"]
            )
            for absence_type in ABSENCE_TYPES
        ],
        min_values=1,
        max_values=1
    )
    
    async def select_callback(i):
        absence_type = next(
            (type for type in ABSENCE_TYPES if type["value"] == select.values[0]),
            None
        )
        
        if absence_type:
            session_cache[user_id]["absence_type"] = absence_type
            modal = AbsenceDetailsModal(user_id, absence_type)
            await i.response.send_modal(modal)
    
    select.callback = select_callback
    view.add_item(select)
    
    await interaction.response.send_message(
        "Please select the type of absence:",
        view=view,
        ephemeral=True
    )

@bot.tree.command(name="create_scrim_button", description="Create a persistent scrim scheduling button")
async def create_scrim_button(interaction: discord.Interaction):
    """Admin command to create a persistent scrim button."""
    # Check for admin permissions
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You need administrator permissions to create a persistent button.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # First acknowledge the interaction to prevent timeout
    await interaction.response.defer(ephemeral=True)

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
    await interaction.followup.send("✅ Persistent scrim button created successfully!", ephemeral=True)

@bot.tree.command(name="setup_absence_button", description="Set up the persistent absence button in this channel")
async def setup_absence_button(interaction: discord.Interaction):
    """Admin command to set up the persistent absence button."""
    # Check for admin permissions
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You need administrator permissions to create a persistent button.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = discord.Embed(
        title="Team Absence Management",
        description="Click the button below to submit an absence notification.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message("Setting up absence button...", ephemeral=True)
    await interaction.channel.send(embed=embed, view=PersistentAbsenceView())
    await interaction.followup.send("Absence button has been set up successfully!", ephemeral=True)

# --- Reminder System ---
async def reminder_check_loop():
    """Background task to check for upcoming reminders."""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            # Fetch upcoming scrims (within next 24 hours) that need reminders
            upcoming_scrims = await db_manager.get_upcoming_scrims(hours_ahead=24)
            
            for scrim in upcoming_scrims:
                # Calculate when the reminder should be sent (30 mins before scrim)
                reminder_time = scrim["start_time"] - datetime.timedelta(minutes=30)
                
                # If it's time to send the reminder (within 1 minute)
                now = datetime.datetime.now()
                if now <= reminder_time <= now + datetime.timedelta(minutes=1):
                    try:
                        # Send the reminder
                        await send_scrim_reminder(scrim)
                        
                        # Mark as sent in database
                        await db_manager.mark_reminder_sent(scrim["id"])
                        
                        logger.info(f"Sent reminder for scrim ID {scrim['id']}")
                    except Exception as e:
                        logger.error(f"Error sending reminder for scrim ID {scrim['id']}: {e}")
            
            # Check every minute
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"Error in reminder check loop: {e}")
            await asyncio.sleep(60)  # Keep trying even if there's an error

async def send_scrim_reminder(scrim: Dict[str, Any]):
    """Send a reminder for a scrim."""
    # Get the channel
    channel_id = scrim["channel_id"]
    channel = bot.get_channel(channel_id)
    
    if not channel:
        logger.error(f"Could not find channel with ID {channel_id} for reminder")
        return
    
    # Get the role ID
    role_id = scrim["role_id"]
    
    # Get the team (for color)
    team = scrim["team"]
    color = TEAM_CONFIG.get(team, {}).get("color", discord.Color(0x3498DB))
    
    # Get the players
    players = scrim["players"]
    if isinstance(players, str):
        players = players.split(',')
    
    # Create player pings if any are specified
    player_pings = "\n".join(players) if players else "Team members"
    
    # Convert the datetime to a Unix timestamp for Discord's timestamp format
    unix_timestamp = int(scrim["start_time"].timestamp())
    
    # Create the reminder message
    reminder_message = (
        f"🔔 **REMINDER** 🔔\n"
        f"<@&{role_id}>\n\n"
        f"Your scrim against **{scrim['opponent']}** starts in 30 minutes at <t:{unix_timestamp}:t>!\n\n"
        f"**Players:**\n{player_pings}\n\n"
        f"Please be ready and in voice channels."
    )
    
    # Create an embed for the reminder
    embed = discord.Embed(
        title=f"⏰ {team} Scrim Reminder",
        description=reminder_message,
        color=color
    )
    
    # Send the reminder
    await channel.send(content=f"<@&{role_id}> **30-MINUTE SCRIM REMINDER**", embed=embed)

# --- Bot Setup and Events ---
@bot.event
async def on_ready():
    """Handle bot startup."""
    try:
        # Initialize database
        await db_manager.initialize()
        
        # Initialize calendar manager
        await calendar_manager.initialize()
        
        # Register persistent views
        bot.add_view(PersistentScrimButton())
        bot.add_view(PersistentAbsenceView())
        
        # Pre-cache channels and roles
        for team_name, config in TEAM_CONFIG.items():
            channel_id = config.get("channel_id")
            role_id = config.get("role_id")
            
            channel = bot.get_channel(channel_id)
            if channel:
                channel_cache[channel_id] = channel
            
            # Guild needed to get roles
            for guild in bot.guilds:
                role = guild.get_role(role_id)
                if role:
                    role_cache[role_id] = role
                    break
        
        # Start reminder check loop
        bot.loop.create_task(reminder_check_loop())
        
        # Sync slash commands
        await bot.tree.sync()
        
        logger.info(f"Bot ready! Logged in as {bot.user}")
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")

@bot.event
async def on_error(event, *args, **kwargs):
    """Global error handler for the bot."""
    logger.error(f"Error in event {event}: {args} {kwargs}")
    
@bot.command()
@commands.is_owner()
async def forcesync(ctx):
    """Force sync slash commands with Discord."""
    await bot.tree.sync()
    await ctx.send("✅ Slash commands have been synced!")

# --- Shutdown Handling ---
@bot.event
async def on_close():
    """Handle bot shutdown."""
    # Close database connection
    await db_manager.close()
    logger.info("Bot shutting down, resources cleaned up")

# --- Run Bot ---
def main():
    """Main entry point for the bot."""
    try:
        bot.run(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        
if __name__ == "__main__":
    main()
