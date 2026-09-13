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
    if message.author.bot:
        return

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=message.content)
        await message.channel.send(response.text)
    except Exception as e:
        print(f"Error generating content: {e}")

    await bot.process_commands(message)

bot.run(os.getenv("DISCORD_TOKEN"))
