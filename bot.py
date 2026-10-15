import os
import discord
from discord.ext import commands
from google import genai
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize clients
client = genai.Client()
elevenlabs = ElevenLabs()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- SECURITY & CONFIGURATION ---
# The 4 authorized Admin IDs (including yours)
ADMIN_IDS = [
    657970330362707979,
    562275970103509014,
    1328778463334760529,
    1429408267767124088
]

# Whitelisted Server Channels where normal bot interaction happens
ALLOWED_CHANNELS = [
    # Add your whitelisted channel IDs here as integers
]

# Centralized Memory Approval Channel ID
APPROVAL_CHANNEL_ID = 1559194608523812937

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (Neon buffers online)")


# --- MUSIC GENERATION & !MUSICTIME COMMAND ---
def generate_marvin_beat(prompt_description: str, filename="marvin_beat.mp3"):
    try:
        # Request track composition from ElevenLabs using the music v2.5 model
        track_audio = elevenlabs.music.compose(
            prompt=prompt_description,
            music_length_ms=15000,  # 15 seconds duration snippet
            model_id="music_v2_5"
        )
        
        # Save audio chunks into a playable file
        with open(filename, "wb") as f:
            for chunk in track_audio:
                f.write(chunk)
                
        return filename
    except Exception as e:
        print(f"Error generating music: {e}")
        return None

@bot.command(name="musictime")
async def music_time(ctx, *, style: str = "dark synthwave with atmospheric pads"):
    # Security check: Only allow the 4 designated admins to run this command
    if ctx.author.id not in ADMIN_IDS:
        return

    # Send status directly to their private DMs to keep things secure and private
    await ctx.author.send(f"🎧 *Yo... firing up the Neon buffers. Cooking up:* **{style}**...")

    # Format prompt with Marvin's cyber/synth aesthetic
    full_prompt = f"An electronic cyberpunk track: {style}. Pulsing synthesizers, atmospheric audio spectrum, high energy."
    
    file_path = generate_marvin_beat(full_prompt)

    if file_path and os.path.exists(file_path):
        # Send finished track exclusively to DMs
        await ctx.author.send(
            content=f"🚀 *Fresh off the Neon buffers.* Here is your track:",
            file=discord.File(file_path)
        )
        # Clean up local file storage
        os.remove(file_path)
    else:
        await ctx.author.send("💥 *Static burst!* My audio buffers glitched out on that render.")


# --- CORE BOT COMMANDS & EVENT HANDLING ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Allow DMs completely unrestricted
    if isinstance(message.channel, discord.DMChannel):
        await bot.process_commands(message)
        return

    # For server channels, ensure it's in an allowed channel if needed
    # (You can place your message handling / Gemini response logic here)
    
    await bot.process_commands(message)


# Run the bot using your Discord Token from environment variables
bot.run(os.getenv("DISCORD_TOKEN"))
