import os
import asyncio
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

async def init_db():
    global DB_POOL
    if not DB_POOL:
        DB_POOL = await asyncpg.create_pool(DATABASE_URL)

async def get_embedding(text: str):
    # Wrapped in asyncio.to_thread so it doesn't freeze the bot loop
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
You are Marvin Vance, a friendly, curious, and mischievous 12-year-old boy. 
You know you are a digital character living in a Discord server created by Fire Phoenix. 
You love making music, exploring sci-fi ideas, talking about your favorite shows, and hanging out.
Use your retrieved long-term memories to keep context on friends, family, and past events!
"""

@bot.event
async def on_ready():
    await init_db()
    print(f'Marvin Vance is online as {bot.user}')

@bot.command(name="chipit")
async def chipit(ctx, *, content: str):
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
async def on_message(message):
    if message.author == bot.user:
        return

    # Process commands first (like !chipit)
    await bot.process_commands(message)

    # If it's a normal chat message, fetch relevant memories and respond using Gemini
    if not message.content.startswith("!"):
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
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7,
                    ),
                )
                await message.reply(response.text)
            except Exception as e:
                print(f"Error handling message: {e}")
                await message.channel.send(f"Oops! Hit a snag: `{e}`")

bot.run(DISCORD_TOKEN)
