import os
import discord
from discord.ext import commands
from google import genai
from memory import save_episode, get_db_connection, generate_embedding

# Initialize environment variables
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Initialize Gemini client
bot_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Configuration: Set your designated Memory Review/Approval channel ID here (as an integer)
APPROVAL_CHANNEL_ID = 0  # Replace with your actual Discord channel ID for approvals

# Whitelist of authorized user IDs who can approve/reject memories or use !chipit
ALLOWED_USER_IDS = [
    1429408267767124088,  # Cody's User ID
    562275970103509014   # Friend's User ID
]

class MemoryApprovalView(discord.ui.View):
    def __init__(self, memory_content: str, speaker: str):
        super().__init__(timeout=None)
        self.memory_content = memory_content
        self.speaker = speaker

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Enforce security so only authorized users can interact with the buttons
        if interaction.user.id not in ALLOWED_USER_IDS:
            await interaction.response.send_message(
                "You are not authorized to approve or reject memories.", 
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Approve Memory", style=discord.ButtonStyle.green, custom_id="approve_memory")
    async def approve_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        # Save into Neon with vector embedding generated via Voyage AI
        try:
            conn = await get_db_connection()
            try:
                vector = await generate_embedding(self.memory_content)
                await conn.execute(
                    """
                    INSERT INTO marvin_episodes (speaker, content, embedding)
                    VALUES ($1, $2, $3);
                    """,
                    self.speaker, self.memory_content, vector
                )
            finally:
                await conn.close()

            await interaction.response.send_message(
                f"Memory approved and permanently etched into Neon by {interaction.user.mention}!", 
                ephemeral=False
            )
        except Exception as e:
            await interaction.response.send_message(f"Error saving memory to database: {e}", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, custom_id="reject_memory")
    async def reject_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(
            f"Memory rejected by {interaction.user.mention}.", 
            ephemeral=False
        )


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Marvin is active with secure manual memory approval workflows enabled!")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

    # Handle direct messages or bot mentions for conversation
    if bot.user in message.mentions or isinstance(message.channel, discord.DMChannel):
        clean_content = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
        
        if not clean_content:
            return

        async with message.channel.typing():
            try:
                response = bot_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=clean_content
                )
                reply_text = response.text
                await message.reply(reply_text)

                # Send interaction to the review channel if configured
                if APPROVAL_CHANNEL_ID != 0:
                    approval_channel = bot.get_channel(APPROVAL_CHANNEL_ID)
                    if approval_channel:
                        embed = discord.Embed(
                            title="🧠 Proposed New Memory",
                            description=f"**Speaker:** {message.author}\n**Content:** {clean_content}\n**Marvin's Reply:** {reply_text}",
                            color=discord.Color.blue()
                        )
                        view = MemoryApprovalView(memory_content=f"User: {clean_content} | Marvin: {reply_text}", speaker=str(message.author))
                        await approval_channel.send(embed=embed, view=view)

            except Exception as e:
                print(f"Error: {e}")
                await message.reply("I encountered a glitch processing that request.")


@bot.command(name="chipit")
async def chipit(ctx, *, memory_text: str):
    """Manually submit a specific fact or memory to be reviewed and approved via !chipit."""
    if ctx.author.id not in ALLOWED_USER_IDS:
        await ctx.send("You are not authorized to use this command.", delete_after=5)
        return

    if APPROVAL_CHANNEL_ID == 0:
        await ctx.send("Please configure the `APPROVAL_CHANNEL_ID` in `bot.py` first.")
        return

    approval_channel = bot.get_channel(APPROVAL_CHANNEL_ID)
    if not approval_channel:
        await ctx.send("Could not find the designated approval channel.")
        return

    embed = discord.Embed(
        title="📝 Manual Memory Proposal",
        description=memory_text,
        color=discord.Color.gold()
    )
    view = MemoryApprovalView(memory_content=memory_text, speaker=str(ctx.author))
    await approval_channel.send(embed=embed, view=view)
    await ctx.send("Memory submitted for review and approval!", delete_after=5)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
