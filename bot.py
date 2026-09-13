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
    print(f"Logged in as {bot.user} - Running clean and smooth!")

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself or other bots to prevent loops
    if message.author.bot:
        return

    # Check if the bot is mentioned or process commands
    if bot.user.mentioned_in(message):
        user_prompt = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
        
        if user_prompt:
            # Generate response from Gemini
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt
            )
            await message.channel.send(response.text)

    await bot.process_commands(message)

# Run the bot using your Discord token
bot.run(os.getenv("DISCORD_TOKEN"))
