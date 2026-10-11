import os
import random
import time
import asyncpg
import discord
from discord.ext import commands
from google import genai
from google.genai import types

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_POOL = None
RESTRICTED_CHANNEL_ID = 1502674164526350398

SYSTEM_INSTRUCTION = """
You are Marvin Vance, a friendly, curious, and mischievous 13-year-old boy.
You are a digital character living in a Discord server created by Fire Phoenix.
You love making music, exploring sci-fi ideas, talking about your favorite shows, and hanging out.
When memories are provided to you from your database, use them to answer accurately about past events!
"""

async def get_embedding(text: str):
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
    )
    return response.embedding.values

@bot.event
async def on_ready():
    global DB_POOL
    try:
        DB_POOL = await asyncpg.create_pool(DATABASE_URL)
        print('Database pool initialized successfully.')
    except Exception as e:
        print(f'Database pool error: {e}')
    print(f'Marvin Vance is online as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.id == RESTRICTED_CHANNEL_ID:
        return

    await bot.process_commands(message)

    if not message.content.startswith("!"):
        try:
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
                            context_memories = "\nRetrieved Memories from Database:\n" + "\n".join([f"- {r['content']}" for r in rows])
                except Exception as e:
                    print(f"Memory retrieval error: {e}")

            full_prompt = f"{context_memories}\n\nUser ({message.author.name}): {message.content}"
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
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
    await ctx.send(f"Memory locked right into my chips, {ctx.author.mention}!")

@bot.command(name="searchmem")
async def searchmem(ctx, *, query: str):
    if not DB_POOL:
        await ctx.send("Database pool isn't connected right now, dude!")
        return

    try:
        embedding = await get_embedding(query)
        vector_str = "[" + ",".join(map(str, embedding)) + "]"
        async with DB_POOL.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT content FROM marvin_episodes 
                ORDER BY embedding <=> $1::vector 
                LIMIT 5;
                """,
                vector_str
            )
            if rows:
                results_text = "\n".join([f"• {r['content']}" for r in rows])
                await ctx.send(f"🔍 **Memory Scan Results for '{query}':**\n{results_text}")
            else:
                await ctx.send(f"🔍 Scanned the hard drive, but couldn't find any memories matching '{query}'!")
    except Exception as e:
        await ctx.send(f"Error scanning memories: {e}")

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
