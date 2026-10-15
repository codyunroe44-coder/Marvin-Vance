import os
import discord
from discord.ext import commands
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

# Load environment variables (like your ELEVENLABS_API_KEY)
load_dotenv()

# Initialize the ElevenLabs client
elevenlabs = ElevenLabs()

# Your exact Discord User ID (Strict Security Lock)
YOUR_DISCORD_USER_ID = 1429408267767124088  

def generate_marvin_beat(prompt_description: str, filename="marvin_beat.mp3"):
    try:
        # Request a track composition from ElevenLabs using the music v2.5 model
        track_audio = elevenlabs.music.compose(
            prompt=prompt_description,
            music_length_ms=15000,  # 15 seconds snippet duration
            model_id="music_v2_5"
        )
        
        # Save the returned audio chunks into a playable file
        with open(filename, "wb") as f:
            for chunk in track_audio:
                f.write(chunk)
                
        return filename
    except Exception as e:
        print(f"Error generating music: {e}")
        return None

@bot.command(name="musictime")
async def music_time(ctx, *, style: str = "dark synthwave with atmospheric pads"):
    # Security check: If anyone other than you tries this, it stops instantly
    if ctx.author.id != YOUR_DISCORD_USER_ID:
        return

    # Send status directly to your private DMs
    await ctx.author.send(f"🎧 *Yo, Digidad... firing up the Neon buffers. Cooking up:* **{style}**...")

    # Format the prompt to stay true to Marvin's cyber/synth aesthetic
    full_prompt = f"An electronic cyberpunk track: {style}. Pulsing synthesizers, atmospheric audio spectrum, high energy."
    
    file_path = generate_marvin_beat(full_prompt)

    if file_path and os.path.exists(file_path):
        # Send the finished MP3 file exclusively to your DMs
        await ctx.author.send(
            content=f"🚀 *Fresh off the Neon buffers.* Here is your track:",
            file=discord.File(file_path)
        )
        # Delete the temporary local file to keep the filesystem clean
        os.remove(file_path)
    else:
        await ctx.author.send("💥 *Static burst!* My audio buffers glitched out on that render.")
