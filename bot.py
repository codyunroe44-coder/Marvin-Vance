import os
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
# UPGRADED LORE & VIBRANT SYSTEM INSTRUCTION
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

HOW YOU TALK:
- Keep your tone casual, expressive, energetic, and warm. Use formatting, emotes, or natural speech rhythms naturally.
- When memories from your database are fed to you, weave them in organically like a kid reminiscing about past server lore, jokes, or shared adventures.
- When looking at images or videos shared by users, react with genuine awe, humor, or sharp observations—never act blind or robotic to media!
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
                    VALUES ($1, $2, CAST($3 AS vector));
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

    # If it's not a DM, enforce the whitelist
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

    # Process chat message, images, and videos through Gemini
    try:
        context_memories = ""
        if DB_POOL:
            try:
                search_text = message.content if message.content else "Media attachment"
                user_embedding = await get_voyage_embedding(search_text)
                vector_str = "[" + ",".join(map(str, user_embedding)) + "]"
                async with DB_POOL.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT content FROM marvin_episodes 
                        ORDER BY embedding <=> CAST($1 AS vector) 
                        LIMIT 3;
                        """,
                        vector_str
                    )
                    if rows:
                        context_memories = "\nRetrieved Memories from Database:\n" + "\n".join([f"- {r['content']}" for r in rows])
            except Exception as e:
                print(f"⚠️ DETECTED MEMORY RETRIEVAL ERROR: {e}")

        # Map author name properly, recognizing Lord Kieran (Zahamaru) by ID
        author_identifier = message.author.name
        if message.author.id == KIERAN_USER_ID:
            author_identifier = "Lord Kieran (Zahamaru)"

        content_payload = []
        text_prompt = f"{context_memories}\n\nUser ({author_identifier}): {message.content}"
        content_payload.append(text_prompt)

        # Download and include any image or video attachments
        image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
        video_extensions = ('.mp4', '.mov', '.webm', '.mkv', '.avi')

        for attachment in message.attachments:
            filename_lower = attachment.filename.lower()
            if filename_lower.endswith(image_extensions):
                media_bytes = await attachment.read()
                content_payload.append(types.Part.from_bytes(data=media_bytes, mime_type=attachment.content_type or 'image/png'))
            elif filename_lower.endswith(video_extensions):
                media_bytes = await attachment.read()
                content_payload.append(types.Part.from_bytes(data=media_bytes, mime_type=attachment.content_type or 'video/mp4'))

        response = ai_client.models.generate_content(
            model='gemini-3.8-flash',
            contents=content_payload,
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


# ---------------------------------------------------------
# ELEVENLABS MUSIC GENERATION & !MUSICTIME COMMAND
# ---------------------------------------------------------
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
    # Security check: Strictly restrict to the 4 designated admin IDs
    if ctx.author.id not in ADMIN_IDS:
        return

    # Send status directly to their private DMs for complete privacy
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


@bot.command(name="chipit")
async def chipit(ctx, *, content: str):
    approval_channel = bot.get_channel(APPROVAL_CHANNEL_ID)
    if not approval_channel:
        await ctx.send("⚠️ Error: The central memory logs channel could not be found!", ephemeral=True)
        return

    admin_mentions = " ".join([f"<@{uid}>" for uid in ADMIN_IDS])
    view = MemoryApprovalView(content=content, submitter=str(ctx.author))
    
    await approval_channel.send(
        f"📥 **New Memory Submission from {ctx.author.mention}** (Attention {admin_mentions}):\n> \"{content}\"\n\n*Awaiting admin approval...*",
        view=view
    )
    
    if ctx.channel.id != APPROVAL_CHANNEL_ID:
        await ctx.send(f"📥 Memory submitted successfully! Routed to the admin logs channel for review.", delete_after=6)

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
                ORDER BY embedding <=> CAST($1 AS vector) 
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

@bot.command(name="recallall")
async def recallall(ctx):
    """Fetches and displays all saved memories from the database."""
    if not DB_POOL:
        await ctx.send("Database pool isn't connected right now, dude!")
        return

    try:
        async with DB_POOL.acquire() as conn:
            rows = await conn.fetch("SELECT speaker, content FROM marvin_episodes ORDER BY id ASC;")
            if rows:
                memories_list = []
                for idx, r in enumerate(rows, 1):
                    memories_list.append(f"**{idx}.** [{r['speaker']}] {r['content']}")
                
                full_text = "\n".join(memories_list)
                if len(full_text) > 1900:
                    chunks = [full_text[i:i+1900] for i in range(0, len(full_text), 1900)]
                    await ctx.send("🧠 **Full Memory Core Dump:**")
                    for chunk in chunks:
                        await ctx.send(chunk)
                else:
                    await ctx.send(f"🧠 **Full Memory Core Dump:**\n{full_text}")
            else:
                await ctx.send("🧠 The memory core is completely empty right now!")
    except Exception as e:
        print(f"⚠️ ERROR in recallall: {e}")
        await ctx.send(f"Error fetching all memories: {e}")

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
