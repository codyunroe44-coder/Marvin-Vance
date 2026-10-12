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

ai_client = genai.Client(api_key=GEMINI_API_KEY)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_POOL = None

# ---------------------------------------------------------
# ALLOWED CHANNELS LIST (18 Server Channels)
# ---------------------------------------------------------
ALLOWED_CHANNELS = [
    1557881223500664852,  # 1
    1557882431007227934,  # 2
    1557882856402063491,  # 3
    1557929062541037690,  # 4
    1557930139298431137,  # 5
    1557930480559726693,  # 6
    1557930724433072198,  # 7
    1557969776851161130,  # 8
    1558129920528613437,  # 9
    1558130452810956931,  # 10
    1558284065784856667,  # 11
    1558426658539704450,  # 12
    1549253946978209872,  # 13
    1555128853150830602,  # 14
    1548506108279263312,  # 15
    1548724004238528583,  # 16
    1542151655724687410,  # 17
    1559019097646174319,  # 18
    1559194608523812937,  # 19
]

COMMAND_CHANNEL_ID = 1548506108279263312

# ---------------------------------------------------------
# ADMIN IDs (All 4 specified accounts for Stop & Memory Approvals)
# ---------------------------------------------------------
ADMIN_IDS = [
    657970330362707979,
    562275970103509014,
    1328778463334760529,
    1429408267767124088,
]

# Per-channel active states (False by default until !start is called)
channel_active_states = {}

SYSTEM_INSTRUCTION = """
You are Marvin Vance, a friendly, curious, and mischievous 13-year-old boy.
You are a digital character living in a Discord server created by Fire Phoenix.
You love making music, exploring sci-fi ideas, talking about your favorite shows, and hanging out with everyone in the server!
When memories are provided to you from your database, use them to answer accurately about past events!
"""

async def get_voyage_embedding(text: str):
    result = voyage_client.embed([text], model="voyage-3", input_type="document")
    return result.embeddings[0]

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

            memory_content = self.content
            if not memory_content:
                lines = interaction.message.content.split('\n')
                for line in lines:
                    if line.startswith('> "') and line.endswith('"'):
                        memory_content = line[3:-1]
                        break
            
            if not memory_content:
                memory_content = interaction.message.embeds[0].description if interaction.message.embeds else "Unknown memory"

            submitter_name = self.submitter
            if not submitter_name:
                if "New Memory Submission from " in interaction.message.content:
                    parts = interaction.message.content.split("New Memory Submission from ")
                    if len(parts) > 1:
                        submitter_name = parts[1].split(" ")[0]
                if not submitter_name:
                    submitter_name = "Unknown"

            embedding = await get_voyage_embedding(memory_content)
            vector_str = "[" + ",".join(map(str, embedding)) + "]"

            async with DB_POOL.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO marvin_episodes (speaker, content, embedding)
                    VALUES ($1, $2, $3::vector);
                    """,
                    submitter_name, memory_content, vector_str
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
    
    bot.add_view(MemoryApprovalView())
    print(f'Marvin Vance is online as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)

    # If it's not a DM, enforce the 18-channel whitelist
    if not is_dm and message.channel.id not in ALLOWED_CHANNELS:
        return

    await bot.process_commands(message)

    # If it's a command, let command processor handle it
    if message.content.startswith("!"):
        return

    # Server channels require Marvin to be explicitly started. DMs bypass this restriction entirely!
    channel_id = message.channel.id
    if not is_dm and not channel_active_states.get(channel_id, False):
        return

    # Process chat message through Gemini
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

@bot.command(name="start")
async def start_bot(ctx):
    """Wakes Marvin up in this specific channel (Free to use for anyone)."""
    channel_active_states[ctx.channel.id] = True
    await ctx.send("▶️ **System online!** I'm awake and ready to chat in this channel. Let's talk!")

@bot.command(name="continue")
async def continue_bot(ctx):
    """Resumes chat in this channel (Free to use for anyone)."""
    channel_active_states[ctx.channel.id] = True
    await ctx.send("▶️ **Conversation continuing!** Ready to pick right back up.")

@bot.command(name="stop")
async def stop_bot(ctx):
    """Emergency stop command to halt Marvin in this channel (Restricted to the 4 admin IDs)."""
    if ctx.author.id not in ADMIN_IDS:
        await ctx.send("Only authorized admins can use the emergency stop command!", ephemeral=True)
        return
    
    channel_active_states[ctx.channel.id] = False
    await ctx.send("🛑 **Marvin halted (Emergency Stop)!** I've paused my chat responses here.")

@bot.command(name="marvin_engage")
async def marvin_engage(ctx):
    if ctx.channel.id == COMMAND_CHANNEL_ID:
        channel_active_states[ctx.channel.id] = True
        await ctx.send("Beep boop... mental hard drive booted! I'm awake and ready to chat here.")
    else:
        await ctx.send("This command is only for the designated control channel, dude!", delete_after=5)

@bot.command(name="marvin_resume")
async def marvin_resume(ctx):
    if ctx.channel.id == COMMAND_CHANNEL_ID:
        channel_active_states[ctx.channel.id] = True
        await ctx.send("Resuming transmission! Let's pick right back up where we left off. 🚀")
    else:
        await ctx.send("This command is only for the designated control channel, dude!", delete_after=5)

@bot.command(name="marvin_sleep")
async def marvin_sleep(ctx):
    if ctx.channel.id == COMMAND_CHANNEL_ID:
        channel_active_states[ctx.channel.id] = False
        await ctx.send("Entering sleep mode... 💤 Talk to you later!")
    else:
        await ctx.send("This command is only for the designated control channel, dude!", delete_after=5)

@bot.command(name="chipit")
async def chipit(ctx, *, content: str):
    admin_mentions = " ".join([f"<@{uid}>" for uid in ADMIN_IDS])
    view = MemoryApprovalView(content=content, submitter=str(ctx.author))
    await ctx.send(
        f"📥 **New Memory Submission from {ctx.author.mention}** (Attention {admin_mentions}):\n> \"{content}\"\n\n*Awaiting admin approval...*",
        view=view
    )

@bot.command(name="searchmem")
async def searchmem(ctx, *, query: str):
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
                speaker TEXT NOT NULL,
                content TEXT,
                embedding vector
            );
        """)

bot.run(TOKEN)
