import os
import asyncpg
import discord
from discord.ext import commands
from discord.ui import View, Button
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

# Restricted channels where the bot is completely blocked
RESTRICTED_CHANNELS = [
    1502674164526350398,
]

# The specific control channel ID
COMMAND_CHANNEL_ID = 1548506108279263312
command_channel_active = True

# Authorized admins: You and your friend
ADMIN_IDS = [
    1429408267767124088,  # Your User ID
    562275970103509014,  # Friend's User ID
]

SYSTEM_INSTRUCTION = """
You are Marvin Vance, a friendly, curious, and mischievous 13-year-old boy.
You are a digital character living in a Discord server created by Fire Phoenix.
You love making music, exploring sci-fi ideas, talking about your favorite shows, and hanging out with everyone in the server!
When memories are provided to you from your database, use them to answer accurately about past events!
"""

async def get_voyage_embedding(text: str):
    result = voyage_client.embed([text], model="voyage-3", input_type="document")
    return result.embeddings[0]

# Persistent View for handling memory approvals across reboots
class MemoryApprovalView(View):
    def __init__(self, content: str = None, submitter: str = None):
        super().__init__(timeout=None)
        self.content = content
        self.submitter = submitter

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅", custom_id="marvin_memory_approve_btn")
    async def approve_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("You don't have permission to approve this memory!", ephemeral=True)
            return

        try:
            await interaction.response.defer()

            # Extract content from the message embed if loaded persistently after restart
            memory_content = self.content
            if not memory_content:
                # Fallback: parse from the message text if view was reloaded
                lines = interaction.message.content.split('\n')
                for line in lines:
                    if line.startswith('> "') and line.endswith('"'):
                        memory_content = line[3:-1]
                        break
            
            if not memory_content:
                memory_content = interaction.message.embeds[0].description if interaction.message.embeds else "Unknown memory"

            embedding = await get_voyage_embedding(memory_content)
            vector_str = "[" + ",".join(map(str, embedding)) + "]"

            async with DB_POOL.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO marvin_episodes (content, embedding)
                    VALUES ($1, $2::vector);
                    """,
                    memory_content, vector_str
                )

            for child in self.children:
                child.disabled = True
            
            await interaction.edit_original_response(
                content=f"✅ **Memory Approved & Locked In by {interaction.user.mention}!**\n> \"{memory_content}\"",
                view=self
            )
        except Exception as e:
            print(f"Error in approve_button: {e}")
            await interaction.followup.send(f"⚠️ Error approving memory: {e}", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❌", custom_id="marvin_memory_deny_btn")
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("You don't have permission to deny this memory!", ephemeral=True)
            return

        try:
            await interaction.response.defer()

            memory_content = self.content
            if not memory_content:
                lines = interaction.message.content.split('\n')
                for line in lines:
                    if line.startswith('> "') and line.endswith('"'):
                        memory_content = line[3:-1]
                        break

            for child in self.children:
                child.disabled = True

            await interaction.edit_original_response(
                content=f"❌ **Memory Denied by {interaction.user.mention}.**\n> \"{memory_content or 'Memory'}\"",
                view=self
            )
        except Exception as e:
            print(f"Error in deny_button: {e}")
            await interaction.followup.send(f"⚠️ Error denying memory: {e}", ephemeral=True)

@bot.event
async def on_ready():
    global DB_POOL
    try:
        DB_POOL = await asyncpg.create_pool(DATABASE_URL)
        await init_db()
        print('Neon Database pool initialized successfully.')
    except Exception as e:
        print(f'Database pool error: {e}')
    
    # Register the persistent view so buttons keep working after a restart
    bot.add_view(MemoryApprovalView())
    print(f'Marvin Vance is online as {bot.user}')

@bot.event
async def on_message(message):
    global command_channel_active

    if message.author == bot.user:
        return

    # 1. Completely ignore restricted channels
    if message.channel.id in RESTRICTED_CHANNELS:
        return

    # 2. If it's the control channel, check if he is currently put to sleep
    if message.channel.id == COMMAND_CHANNEL_ID and not command_channel_active and not message.content.startswith("!"):
        return

    # Process commands first so control commands always work
    await bot.process_commands(message)

    # Handle standard chat messages
    if not message.content.startswith("!"):
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

@bot.command(name="marvin_engage")
async def marvin_engage(ctx):
    """Boots up Marvin in the designated command channel."""
    global command_channel_active
    if ctx.channel.id == COMMAND_CHANNEL_ID:
        command_channel_active = True
        await ctx.send("Beep boop... mental hard drive booted! I'm awake and ready to chat here.")
    else:
        await ctx.send("This command is only for the designated control channel, dude!", delete_after=5)

@bot.command(name="marvin_resume")
async def marvin_resume(ctx):
    """Resumes the conversation in the designated command channel."""
    global command_channel_active
    if ctx.channel.id == COMMAND_CHANNEL_ID:
        command_channel_active = True
        await ctx.send("Resuming transmission! Let's pick right back up where we left off. 🚀")
    else:
        await ctx.send("This command is only for the designated control channel, dude!", delete_after=5)

@bot.command(name="marvin_sleep")
async def marvin_sleep(ctx):
    """Puts Marvin to sleep in the designated command channel."""
    global command_channel_active
    if ctx.channel.id == COMMAND_CHANNEL_ID:
        command_channel_active = False
        await ctx.send("Entering sleep mode... 💤 Talk to you later!")
    else:
        await ctx.send("This command is only for the designated control channel, dude!", delete_after=5)

@bot.command(name="chipit")
async def chipit(ctx, *, content: str):
    """Anyone can submit a memory, pinging admins and triggering approval buttons."""
    admin_mentions = f"<@1429408267767124088> <@562275970103509014>"
    view = MemoryApprovalView(content=content, submitter=str(ctx.author))
    await ctx.send(
        f"📥 **New Memory Submission from {ctx.author.mention}** (Attention {admin_mentions}):\n> \"{content}\"\n\n*Awaiting admin approval...*",
        view=view
    )

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
