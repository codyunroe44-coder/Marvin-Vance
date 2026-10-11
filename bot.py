import os
import random
import time
import asyncpg
import discord
from discord.ext import commands
from google import genai
from google.genai import types

# Configuration & Setup
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize the modern Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Database Pool
DB_POOL = None

# State controls
RESTRICTED_CHANNEL_ID = 1502674164526350398

SYSTEM_INSTRUCTION = """
You are Marvin Vance, a friendly, curious, and mischievous 13-year-old boy.
You are a digital character living in a Discord server created by Fire Phoenix.
You love making music, exploring sci-fi ideas, talking about your favorite shows, and hanging out.
Use your retrieved long-term memories to keep context on friends, family, and past events!
"""

async def get_embedding(text: str):
    response = client.models.embed_content(
        model="text-embedding-004",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
    )
    return response.embedding.values

@bot.event
async def on_ready():
    global DB_POOL
    DB_POOL = await asyncpg.create_pool(DATABASE_URL)
    print(f'Marvin Vance is online as {bot.user}')

@bot.event
async def on_message(message):
    # 1. Ignore own messages
    if message.author == bot.user:
        return

    # 2. Completely ignore the restricted channel
    if message.channel.id == RESTRICTED_CHANNEL_ID:
        return

    # 3. Process commands first
    await bot.process_commands(message)

    # 4. Handle standard chat messages
    if not message.content.startswith("!"):
        try:
            # Search database for relevant memories if pool is ready
            context_memories = ""
            if DB_POOL:
                try:
                    user_embedding = await get_embedding(message.content)
                    vector_str = "[" + ",".join(map(str, user_embedding)) + "]"
                    async with DB_POOL.acquire() as conn:
                        rows = await conn.fetch(
                            """
                            SELECT content FROM marvin_episodes 
                            ORDER BY embedding <=> $1::vector 
                            LIMIT 3;
                            """,
                            vector_str
                        )
                        if rows:
                            context_memories = "\nRetrieved Memories:\n" + "\n".join([f"- {r['content']}" for r in rows])
                except Exception as e:
                    print(f"Memory retrieval error: {e}")

            full_prompt = f"{context_memories}\n\nUser ({message.author.name}): {message.content}"
            
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                ),
            )
            
            if response and response.text:
                await message.channel.send(response.text)
        except Exception as e:
            print(f"Gemini generation error: {e}")

@bot.command(name="chipit")
async def chipit(ctx, *, content: str):
    if ctx.author.id != 152674164526350398: 
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

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Whoa there! Slow down. Try again in {error.retry_after:.1f} seconds.", delete_after=5)
    else:
        raise error

async def init_db():
    async with DB_POOL.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS marvin_episodes (
                id SERIAL PRIMARY KEY,
                content TEXT,
                embedding vector
            );
        """)

bot.run(TOKEN)
