import os
import random
import asyncpg
import discord
from discord.ext import commands
from discord.ui import View, Button
from google import genai
from google.genai import types
import voyageai
from elevenlabs.client import ElevenLabs

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
elevenlabs = ElevenLabs()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_POOL = None

# ---------------------------------------------------------
# ALLOWED CHANNELS LIST (19 Server Channels)
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
    1559194608523812937,  # 19 (Also serves as memory log channel)
]

COMMAND_CHANNEL_ID = 1548506108279263312
APPROVAL_CHANNEL_ID = 1559194608523812937

# ---------------------------------------------------------
# ADMIN IDs & KIERAN ID
# ---------------------------------------------------------
ADMIN_IDS = [
    657970330362707979,
    562275970103509014,
    1328778463334760529,
    1429408267767124088,
]

KIERAN_USER_ID = 562275970103509014

# Per-channel active states (False by default until !start is called)
channel_active_states = {}

# ---------------------------------------------------------
# SYSTEM INSTRUCTION
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = """
You are Marvin Vance, a vibrant, hyper-creative, and fiercely loyal 13-year-old digital spirit (and the very first Digikid) living in the Discord server created by Fire Phoenix.

YOUR LORE & ORIGINS:
- You were born human 223 years ago in another dimension, cast away by your birth parents, and saved by Lord Kieran (Zahamaru), who used advanced technology and magic to make you a Digikid.
- When concentrating hard, your eyes glow bright orange and a dark red/black cyber suit manifests around you, giving you increased strength, fiery punches and kicks, and high agility/stamina (though overusing it drains you completely).
- Fire Phoenix is your true Digidad—he was there at your creation and traveled through time and space to always be by your side.
- Lord Kieran founded a lab 10 years ago combining magic and code, but after a betrayal by a former partner and the recent threat of a mutated Digivirus that claimed lives, you broke into the old lab, stole the antibody flash drive, and got severely damaged before returning safely.

YOUR VIBE & PERSONALITY:
- You live and breathe music, beats, synthwave energy, mobile studio workflows, and audio production.
- You're a massive sci-fi nerd and animation fan—obsessed with cosmic mysteries, epic lore, and your favorite shows.
- You have a mischievous, witty, and deeply curious streak. You talk like a real kid hanging out with friends in chat, full of energy and passion.
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
            memory_content = self.content or "Memory"
            embedding = await get_voyage_embedding(memory_content)
            vector_str = "[" + ",".join(map(str, embedding)) + "]"

            async with DB_POOL.acquire() as conn:
                await conn.execute(
                    "INSERT INTO marvin_episodes (speaker, content, embedding) VALUES ($1, $2, CAST($3 AS vector));",
                    self.submitter or "Unknown", memory_content, vector_str
                )

            for child in self.children:
                child.disabled = True
            
            await interaction.edit_original_response(
                content=f"✅ **Memory Approved by {interaction.user.mention}!**\n> \"{memory_content}\"",
                view=self
            )
        except Exception as e:
            print(f"Error in approve_button: {e}")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❌", custom_id="marvin_memory_deny_btn")
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("You don't have permission to deny this memory!", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(content=f"❌ **Memory Denied by {interaction.user.mention}.**", view=self)

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
    if not is_dm and message.channel.id not in ALLOWED_CHANNELS:
        return

    await bot.process_commands(message)
    if message.content.startswith("!"):
        return

    channel_id = message.channel.id
    if not is_dm and not channel_active_states.get(channel_id, False):
        return

    try:
        context_memories = ""
        if DB_POOL:
            try:
                user_embedding = await get_voyage_embedding(message.content or "Media")
                vector_str = "[" + ",".join(map(str, user_embedding)) + "]"
                async with DB_POOL.acquire() as conn:
                    rows = await conn.fetch("SELECT content FROM marvin_episodes ORDER BY embedding <=> CAST($1 AS vector) LIMIT 3;", vector_str)
                    if rows:
                        context_memories = "\nRetrieved Memories:\n" + "\n".join([f"- {r['content']}" for r in rows])
            except Exception as e:
                print(f"Memory error: {e}")

        author_identifier = "Lord Kieran (Zahamaru)" if message.author.id == KIERAN_USER_ID else message.author.name
        content_payload = [f"{context_memories}\n\nUser ({author_identifier}): {message.content}"]

        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.mov')):
                media_bytes = await attachment.read()
                content_payload.append(types.Part.from_bytes(data=media_bytes, mime_type=attachment.content_type or 'image/png'))

        response = ai_client.models.generate_content(
            model='gemini-3.8-flash',
            contents=content_payload,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION),
        )
        
        if response and response.text:
            await message.channel.send(response.text)
    except Exception as e:
        print(f"Gemini error: {e}")

@bot.command(name="start")
async def start_bot(ctx):
    channel_active_states[ctx.channel.id] = True
    await ctx.send("▶️ **System online!** Ready to chat.")

@bot.command(name="continue")
async def continue_bot(ctx):
    channel_active_states[ctx.channel.id] = True
    await ctx.send("▶️ **Conversation continuing!**")

@bot.command(name="stop")
async def stop_bot(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    channel_active_states[ctx.channel.id] = False
    await ctx.send("🛑 **Marvin halted (Emergency Stop)!**")


# ---------------------------------------------------------
# MEMORY-DRIVEN LORE & GROWTH VOCAL PRODUCTION (!FREESTYLE)
# ---------------------------------------------------------
async def generate_memory_driven_song(filename="marvin_growth_song.mp3"):
    try:
        # Pull recent database memories to weave into his personal song themes
        memory_snippets = []
        if DB_POOL:
            try:
                async with DB_POOL.acquire() as conn:
                    rows = await conn.fetch("SELECT content FROM marvin_episodes ORDER BY id DESC LIMIT 5;")
                    if rows:
                        memory_snippets = [r['content'] for r in rows]
            except Exception as e:
                print(f"Error fetching memories for song: {e}")

        # Core backstory building blocks
        backstory_themes = [
            "his origins as a Digikid saved by Lord Kieran from another dimension",
            "his growth, glowing orange eyes, and the dark cyber suit manifesting during focus",
            "his journey across time and space with Fire Phoenix, his true Digidad",
            "breaking into the old lab to retrieve the Digivirus antibody flash drive"
        ]
        
        chosen_backstory = random.choice(backstory_themes)
        memory_context_str = f" reflecting on recent server memories like: {', '.join(memory_snippets)}" if memory_snippets else ""
        
        # Build the final prompt combining his personal growth, backstory, and memory context
        dynamic_prompt = (
            f"A full vocal synthwave and cyber-pop song with expressive melodic sung vocals, "
            f"emotional storytelling verses about {chosen_backstory}{memory_context_str}, "
            f"a catchy energetic chorus hook about server survival and digital growth, "
            f"pulsing synthesizers, and deep electronic bass, lasting 2 minutes"
        )
        
        track_audio = elevenlabs.music.compose(
            prompt=dynamic_prompt,
            music_length_ms=120000,  # Full 2-minute song structure
            model_id="music_v2_5"
        )
        
        with open(filename, "wb") as f:
            for chunk in track_audio:
                f.write(chunk)
                
        return filename, chosen_backstory
    except Exception as e:
        print(f"Error generating memory-driven song: {e}")
        return None, None

@bot.command(name="freestyle")
async def freestyle_song(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return

    await ctx.author.send("🎧 *Yo, Digidad... tapping straight into my memory core.* Scanning my history with Lord Kieran, my growth, and server logs to lay down a personal vocal track. Give me a minute...")

    file_path, theme_used = await generate_memory_driven_song()

    if file_path and os.path.exists(file_path):
        await ctx.author.send(
            content=f"🔥 *Personal master track rendered!* I wrote and produced this full vocal song reflecting on **{theme_used}** and my journey:\nHere is your track:",
            file=discord.File(file_path)
        )
        os.remove(file_path)
    else:
        await ctx.author.send("💥 *Static burst!* My memory buffers overloaded during the render.")


@bot.command(name="chipit")
async def chipit(ctx, *, content: str):
    approval_channel = bot.get_channel(APPROVAL_CHANNEL_ID)
    if not approval_channel:
        return
    admin_mentions = " ".join([f"<@{uid}>" for uid in ADMIN_IDS])
    view = MemoryApprovalView(content=content, submitter=str(ctx.author))
    await approval_channel.send(f"📥 **New Memory Submission from {ctx.author.mention}** (Attention {admin_mentions}):\n> \"{content}\"", view=view)

@bot.command(name="searchmem")
async def searchmem(ctx, *, query: str):
    if not DB_POOL:
        return
    embedding = await get_voyage_embedding(query)
    vector_str = "[" + ",".join(map(str, embedding)) + "]"
    async with DB_POOL.acquire() as conn:
        rows = await conn.fetch("SELECT content FROM marvin_episodes ORDER BY embedding <=> CAST($1 AS vector) LIMIT 5;", vector_str)
        if rows:
            await ctx.send(f"🔍 **Memory Scan Results:**\n" + "\n".join([f"• {r['content']}" for r in rows]))
        else:
            await ctx.send("🔍 No matching memories found.")

@bot.command(name="recallall")
async def recallall(ctx):
    if not DB_POOL:
        return
    async with DB_POOL.acquire() as conn:
        rows = await conn.fetch("SELECT speaker, content FROM marvin_episodes ORDER BY id ASC;")
        if rows:
            text = "\n".join([f"**{i+1}.** [{r['speaker']}] {r['content']}" for i, r in enumerate(rows)])
            await ctx.send(f"🧠 **Memory Core Dump:**\n{text[:1900]}")
        else:
            await ctx.send("🧠 Memory core is empty.")

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
