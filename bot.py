import os
import discord
from discord.ext import commands
from google import genai

# Initialize Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize Gemini Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} - Chat mode active!")

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself to prevent infinite loops
    if message.author.bot:
        return

    # Ignore prefix commands (like !ping) so they don't trigger AI responses twice
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    try:
        # Send every chat message directly to Gemini
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=message.content
        )
        await message.channel.send(response.text)
    except Exception as e:
        print(f"Error generating content: {e}")

    # Process any other standard commands
    await bot.process_commands(message)

# Run the bot using your Discord token
bot.run(os.getenv("DISCORD_TOKEN"))
