import discord

REPORT_CHANNEL_ID = 1399853992959283372  # replace with your staff-only channel ID

class ReportModal(discord.ui.Modal, title="Anonymous Report"):
    report = discord.ui.TextInput(
        label="What would you like to report?",
        style=discord.TextStyle.paragraph,
        placeholder="Be as detailed as possible...",
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        report_channel = interaction.client.get_channel(REPORT_CHANNEL_ID)
        embed = discord.Embed(
            title="📢 New Anonymous Report",
            description=self.report.value,
            color=discord.Color.orange()
        )
        embed.set_footer(text="Submitted via Anonymous Report button")
        await report_channel.send(embed=embed)
        await interaction.response.send_message("✅ Your report has been sent anonymously.", ephemeral=True)

class AnonymousReportButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Submit Anonymous Report", style=discord.ButtonStyle.danger, custom_id="anon_report")
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

# Optional: use this in your main bot to send the message
async def post_anon_button(bot, channel_id):
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(
            content="If you need to report something anonymously, click the button below:",
            view=AnonymousReportButton()
        )
