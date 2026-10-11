import os
import asyncpg
import discord
from discord.ext import commands
from google import genai
from google.genai import types
import voyageai

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")

# Initialize modern clients
ai_client = genai.Client(api_key=GEMINI_API_KEY)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_POOL = None

# List of restricted channels where the bot will completely ignore messages
RESTRICTED_CHANNELS = [
    1502674164526350398,
    # Add any other restricted channel IDs here as needed
]

# State tracking for the 25-message active session limit
active_session = {
    "active": False,
    "messages_remaining": 0,
    "channel_id": None
}

SYSTEM_INSTRUCTION = """
You are Marvin Vance, a friendly, curious, and mischievous 13-year-old boy.
You are a digital character living in a Discord server created by Fire Phoenix.
You love making music, exploring sci-fi ideas, talking about your favorite shows, and hanging out with everyone in the server!
When memories are provided to you from your database, use them to answer accurately about past events!
"""

async def get_voyage_embedding(text: str):
    result = voyage_client.embed([text], model="voyage-3", input_type="document")
    return result.embeddings[0]

@bot.event
async def on_ready():
    global DB_POOL
    try:
        DB_POOL = await asyncpg.create_pool(DATABASE_URL)
        print('Neon Database pool initialized successfully.')
    except Exception as e:
        print(f'Database pool error: {e}')
    print(f'Marvin Vance is online as {bot.user}')

@bot.event
async def on_message(message):
    global active_session

    if message.author == bot.user:
        return

    # Completely ignore restricted channels
    if message.channel.id in RESTRICTED_CHANNELS:
        return

    await bot.process_commands(message)

    # Handle standard server chat messages under the 25-message active session limit
    if not message.content.startswith("!"):
        if active_session["active"] and active_session["channel_id"] == message.channel.id:
            try:
                context_memories = ""
                if DB_POOL:
                    try:
                        user_embedding = await get_voyage_embedding(message.content)
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
                
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                    ),
                )
                
                if response and response.text:
                    await message.channel.send(response.text)
                    
                    # Decrement active session counter
                    active_session["messages_remaining"] -= 1
                    if active_session["messages_remaining"] <= 0:
                        active_session["active"] = False
                        await message.channel.send("Beep boop... reached my 25-message limit, going back to sleep! Wake me up with `!marvin_engage` when you need me again.")
            except Exception as e:
                print(f"Gemini generation error: {e}")

@bot.command(name="marvin_engage")
async def marvin_engage(ctx):
    """Boots up an active 25-message chat session in the current channel."""
    global active_session
    active_session["active"] = True
    active_session["messages_remaining"] = 25
    active_session["channel_id"] = ctx.channel.id
    await ctx.send("Beep boop... booting up mental hard drive... 💾 Session started! I'm ready to chat with everyone for the next 25 messages.")

@bot.command(name="marvin_sleep")
async def marvin_sleep(ctx):
    """Manually ends the active chat session."""
    global active_session
    active_session["active"] = False
    await ctx.send("Entering sleep mode... 💤 Catch you later!")

@bot.command(name="chipit")
async def chipit(ctx, *, content: str):
    if ctx.author.id != 152674164526350398: 
        await ctx.send("You don't have permission to add memories to my database.", delete_after=5)
        return

    await init_db()
    embedding = await get_voyage_embedding(content)
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
    """Explicitly searches the vector database for a query."""
    if not DB_POOL:
        await ctx.send("Database pool isn't connected right now, dude!")
        return

    try:
        embedding = await get_voyage_embedding(query)
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
