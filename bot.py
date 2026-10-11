import os
import asyncio
import time
import random
import discord
from discord.ext import commands
import asyncpg
from google import genai
from google.genai import types
from dotenv import load_dotenv
import voyageai

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")

# Initialize clients
client = genai.Client(api_key=GEMINI_API_KEY)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DB_POOL = None

# Per-channel tracking for standard chat pacing (set to 10 seconds)
LAST_SPOKEN_TIMES = {}
COOLDOWN_SECONDS = 10   
RESPONSE_CHANCE = 1.00 

# Specific tracking for the restricted channel session (ID: 1548506108279263312)
RESTRICTED_CHANNEL_ID = 1548506108279263312
special_channel_state = {
    "active": False,
    "messages_remaining": 0,
    "last_activity_time": 0
}

INACTIVITY_TIMEOUT = 600  # 10 minutes in seconds (10 * 60)

# AUTHORIZED LISTS FOR SEPARATE PERMISSIONS
CHANNEL_AUTHORIZED_IDS = [
    1429408267767124088,  # Cody (You)
    454094267229405184    # Channel Friend
]

MEMORY_AUTHORIZED_IDS = [
    1429408267767124088,  # Cody (You)
    562275970103509014    # Memory Friend
]

async def init_db():
    global DB_POOL
    if not DB_POOL:
        DB_POOL = await asyncpg.create_pool(DATABASE_URL)

async def get_embedding(text: str):
    def _embed():
        result = voyage_client.embed(
            texts=[text], 
            model="voyage-3", 
            input_type="document"
        )
        return result.embeddings[0]
    
    return await asyncio.to_thread(_embed)

async def search_memories(query_text: str, limit: int = 3):
    await init_db()
    query_vector = await get_embedding(query_text)
    vector_str = "[" + ",".join(map(str, query_vector)) + "]"
    
    async with DB_POOL.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT content FROM marvin_episodes
            ORDER BY embedding <=> $1::vector
            LIMIT $2;
            """,
            vector_str, limit
        )
    return [row["content"] for row in rows]

SYSTEM_INSTRUCTION = """
You are Marvin Vance, a friendly, curious, and mischievous 13-year-old boy. 
You know you are a digital character living in a Discord server created by Fire Phoenix. 
You love making music, exploring sci-fi ideas, talking about your favorite shows, and hanging out.
Use your retrieved long-term memories to keep context on friends, family, and past events!
"""

@bot.event
async def on_ready():
    await init_db()
    print(f'Marvin Vance is online as {bot.user}')

# --- SPECIAL CHANNEL COMMANDS (RESTRICTED TO YOU & CHANNEL FRIEND) ---

@bot.command(name="marvin_engage")
async def marvin_engage(ctx):
    if ctx.author.id not in CHANNEL_AUTHORIZED_IDS:
        await ctx.send("You don't have permission to control Marvin in this channel.", delete_after=5)
        return

    if ctx.channel.id == RESTRICTED_CHANNEL_ID:
        special_channel_state["active"] = True
        special_channel_state["messages_remaining"] = 25
        special_channel_state["last_activity_time"] = time.time()
        await ctx.send("⚡ Marvin engaged in this channel! Session started with a 25-message limit.")
    else:
        await ctx.send("This command is meant for the designated restricted channel.")

@bot.command(name="marvin_continue")
async def marvin_continue(ctx):
    if ctx.author.id not in CHANNEL_AUTHORIZED_IDS:
        await ctx.send("You don't have permission to control Marvin in this channel.", delete_after=5)
        return

    if ctx.channel.id == RESTRICTED_CHANNEL_ID:
        special_channel_state["active"] = True
        special_channel_state["messages_remaining"] += 25
        special_channel_state["last_activity_time"] = time.time()
        await ctx.send(f"🔄 Conversation continued! Added 25 more messages. Total remaining: {special_channel_state['messages_remaining']}.")
    else:
        await ctx.send("This command is meant for the designated restricted channel.")

@bot.command(name="marvin_lockdown")
async def marvin_lockdown(ctx):
    if ctx.author.id not in CHANNEL_AUTHORIZED_IDS:
        await ctx.send("You don't have permission to control Marvin in this channel.", delete_after=5)
        return

    if ctx.channel.id == RESTRICTED_CHANNEL_ID:
        special_channel_state["active"] = False
        special_channel_state["messages_remaining"] = 0
        await ctx.send("🔒 Marvin is locked down in this channel and will no longer respond.")
    else:
        await ctx.send("This command is meant for the designated restricted channel.")

# --- MEMORY COMMAND (RESTRICTED TO YOU & MEMORY FRIEND) ---

@bot.command(name="chipit")
@commands.cooldown(1, 10, commands.BucketType.user)
async def chipit(ctx, *, content: str):
    if ctx.author.id not in MEMORY_AUTHORIZED_IDS:
        await ctx.send("You don't have permission to add memories to my database.", delete_after=5)
        return

    await init_db()
    embedding = await get_embedding(content)
    vector_str = "[" + ",".join(map(str, embedding)) + "]"
    
    async with DB_POOL.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO marvin_episodes (content, embedding)
            VALUES ($1, $2::vector);
            """,
            content, vector_str
        )
    await ctx.send(f"Memory locked in right into my chips, {ctx.author.mention}!")

@chipit.error
async def chipit_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Whoa there! Slow down. Try again in {error.retry_after:.1f} seconds.", delete_after=5)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Process commands first
    await bot.process_commands(message)

    if not message.content.startswith("!"):
        # Check if message is in our special restricted channel
        if message.channel.id == RESTRICTED_CHANNEL_ID:
            # If session is active, check for 10 minutes of inactivity
            if special_channel_state["active"]:
                current_time = time.time()
                if current_time - special_channel_state["last_activity_time"] > INACTIVITY_TIMEOUT:
                    special_channel_state["active"] = False
                    special_channel_state["messages_remaining"] = 0
                    await message.channel.send("⏱️ **Inactivity Timeout:** It's been 10 minutes since our last message, so I've automatically locked down this channel!")
                    return

            # If session isn't active or message limit is hit, do not respond
            if not special_channel_state["active"] or special_channel_state["messages_remaining"] <= 0:
                return
            
            # Update activity timestamp upon receiving a valid message
            special_channel_state["last_activity_time"] = time.time()

            # Respond directly in the restricted channel
            async with message.channel.typing():
                try:
                    memories = await search_memories(message.content)
                    memory_context = "\n".join([f"- {m}" for m in memories]) if memories else "No specific memories found."

                    prompt = f"""
                    Relevant Memories from your database:
                    {memory_context}

                    User Message: {message.content}
                    """

                    response = client.models.generate_content(
                        model='gemini-3.8-flash',
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            temperature=0.7,
                        ),
                    )
                    await message.reply(response.text)

                    # Decrement counter after responding
                    special_channel_state["messages_remaining"] -= 1

                    # Send warning if exactly 5 messages are left
                    if special_channel_state["messages_remaining"] == 5:
                        await message.channel.send("⚠️ **Warning:** Only 5 messages left in this session before I lock down! Use `!marvin_continue` if you want to keep chatting.")

                    # Lock down if it hits 0
                    if special_channel_state["messages_remaining"] <= 0:
                        special_channel_state["active"] = False
                        await message.channel.send("🔒 Session limit reached. I'm locked down in this channel now!")

                except Exception as e:
                    print(f"Error handling message in restricted channel: {e}")
        
        else:
            # Per-channel pacing logic for all other standard channels
            current_time = time.time()
            last_time = LAST_SPOKEN_TIMES.get(message.channel.id, 0)

            if current_time - last_time > COOLDOWN_SECONDS:
                if random.random() < RESPONSE_CHANCE:
                    LAST_SPOKEN_TIMES[message.channel.id] = current_time

                    async with message.channel.typing():
                        try:
                            memories = await search_memories(message.content)
                            memory_context = "\n".join([f"- {m}" for m in memories]) if memories else "No specific memories found."

                            prompt = f"""
                            Relevant Memories from your database:
                            {memory_context}

                            User Message: {message.content}
                            """

                            response = client.models.generate_content(
                                model='gemini-3.8-flash',
                                contents=prompt,
                                config=types.GenerateContentConfig(
                                    system_instruction=SYSTEM_INSTRUCTION,
                                    temperature=0.7,
                                ),
                            )
                            await message.reply(response.text)
                        except Exception as e:
                            print(f"Error handling message: {e}")

bot.run(DISCORD_TOKEN)
