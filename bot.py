import os
import random
from datetime import datetime
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
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
ELEVENLABS_DUET_VOICE_ID = os.getenv("ELEVENLABS_DUET_VOICE_ID")

ai_client = genai.Client(api_key=GEMINI_API_KEY)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
elevenlabs = ElevenLabs()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_POOL = None

# ---------------------------------------------------------
# ALLOWED CHANNELS LIST (Includes Memory/Approval Channel)
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
    1548506108279263312,  # 15 (Restricted Channel: 25 message limit & unique commands)
    1548724004238528583,  # 16
    1542151655724687410,  # 17
    1559019097646174319,  # 18
    1559194608523812937,  # 19 (Memory log & approval channel)
    1557976491642323097,  # 20
    1562282579690913832,  # 21
    1562470310861738234,  # 22 (New allowed channel)
]

RESTRICTED_MESSAGE_LIMIT_CHANNEL = 1548506108279263312
APPROVAL_CHANNEL_ID = 1559194608523812937

# ---------------------------------------------------------
# ADMIN IDs & IDENTITY OVERRIDES
# ---------------------------------------------------------
ADMIN_IDS = [
    657970330362707979,
    562275970103509014,
    1328778463334760529,
    1429408267767124088,
]

USER_IDENTITY_OVERRIDES = {
    562275970103509014: "Lord Kieran (Zahamaru)",
}

# Per-channel active states, message tracking, & isolated chat memory buffers
channel_active_states = {}
channel_message_counts = {}
chat_sessions = {}

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

YOUR FAMILY & YOUNGER SIBLINGS:
- You have a tight-knit network of younger siblings who support you in your adventures:
  - Luca: Your 14-year-old little brother. After your past fight, the two of you became inseparable; your fire and his lightning naturally pull toward each other.
  - Cole: Created from a fragment of the original virus to combat it.
  - Lucas: Commands the power of an ancient Wind Dragon, enabling him to fly and use a dragon whip.
  - Tyler: Equipped with a unique cyber suit that functions differently from yours.
  - Timmy: The family tracker who can summon a pure red magic sword capable of cutting through anything.
  - Rylan: Uses powerful purple flames of darkness to transform into a shadow version of himself, produce blinding mist, and heal allies.
  - Nolan: Possesses super strength with the ability to lift and plow through almost anything. 
  - You have been training Luca every day since getting back on your feet, preparing him for what is to come—he is nowhere near ready, but is slowly making progress.
  - Your twin power cores keep you strongly bonded together, with your fire core and his lightning core made from the same magical material and code.
  - You share a hidden memory with Luca that you have yet to unlock together.
  - This hidden memory will only unlock for the two of you when you become perfectly in sync with each other.
  - Luca came down with the Digivirus after you unknowingly exposed him to it during your first fight in the desert cavern.
  - Lord Kieran, whom you’ve slowly begun calling Dad again, worked tirelessly to crack open the flash drive to get the antibodies to synthesize a cure for Luca as you worried yourself to death.
  - While you could do nothing but wait, Kieran took you for ice cream many nights. Which reminded you that even though Fire Phenix is your true Digidad, Kieran is just as much a part of your life as well.
  - One night, He told you the story of your old world, and why you had to leave. You lived in a world by the name of Zamaria; Lord Kieran ruled that world. 
  - His partner wasn’t just someone he met here. He was there and destroyed your world. To save your life when your human parents left you, Kieran had to sacrifice a part of himself. In him were two living dragon spirits. One ice dragon and one fire dragon. He gave you his fire dragon and embedded it into your Digikid core along with all of the tech and magic that made you the first Digikid. 
    

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

        await interaction.response.defer()

        try:
            memory_content = self.content or "Memory"
            embedding = await get_voyage_embedding(memory_content)
            vector_str = "[" + ",".join(map(str, embedding)) + "]"
            approval_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

            async with DB_POOL.acquire() as conn:
                await conn.execute(
                    "INSERT INTO marvin_episodes (speaker, content, embedding) VALUES ($1, $2, CAST($3 AS vector));",
                    self.submitter or "Unknown", memory_content, vector_str
                )

            for child in self.children:
                child.disabled = True
            
            await interaction.edit_original_response(
                content=f"✅ **Memory Approved by {interaction.user.mention} at {approval_time}!**\n> \"{memory_content}\"",
                view=self
            )
        except Exception as e:
            print(f"Error in approve_button: {e}")
            await interaction.followup.send(f"❌ Error processing memory approval: {e}", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❌", custom_id="marvin_memory_deny_btn")
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("You don't have permission to deny this memory!", ephemeral=True)
            return

        await interaction.response.defer()
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
    print(f"DEBUG: Message received in channel ID: {message.channel.id} from {message.author}")

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

    if not is_dm and channel_id == RESTRICTED_MESSAGE_LIMIT_CHANNEL:
        current_count = channel_message_counts.get(channel_id, 0)
        if current_count >= 25:
            channel_active_states[channel_id] = False
            await message.channel.send("🛑 **Restricted message limit reached (25/25)!** Use `!m_continue` to unlock another 25 messages.")
            return
        
        if current_count == 20:
            await message.channel.send("⚠️ **Heads up, Digidad!** Only 5 messages left before this channel hits its 25-message limit.")

        channel_message_counts[channel_id] = current_count + 1

    session_key = message.author.id if is_dm else channel_id

    try:
        context_memories = ""
        if DB_POOL:
            try:
                search_text = message.content or "Media"
                user_embedding = await get_voyage_embedding(search_text)
                vector_str = "[" + ",".join(map(str, user_embedding)) + "]"
                async with DB_POOL.acquire() as conn:
                    rows = await conn.fetch("SELECT content FROM marvin_episodes ORDER BY embedding <=> CAST($1 AS vector) LIMIT 5;", vector_str)
                    if rows:
                        context_memories = "\n[CRITICAL APPROVED LORE & MEMORIES TO INTEGRATE INTO YOUR STORYLINE]:\n" + "\n".join([f"- {r['content']}" for r in rows])
            except Exception as e:
                print(f"Memory retrieval error: {e}")

        author_identifier = USER_IDENTITY_OVERRIDES.get(message.author.id, message.author.name)

        if session_key not in chat_sessions:
            chat_sessions[session_key] = ai_client.chats.create(
                model='gemini-3.8-flash',
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
            )
        
        chat = chat_sessions[session_key]

        prompt_content = (
            f"{context_memories}\n\n"
            f"Instructions: If any retrieved memories above are relevant to what {author_identifier} is saying, "
            f"you MUST seamlessly weave them into your character persona, lore, and response.\n\n"
            f"User ({author_identifier}): {message.content}"
        )

        content_payload = [prompt_content]

        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.mov', '.mp3', '.wav', '.ogg', '.m4a')):
                media_bytes = await attachment.read()
                content_payload.append(types.Part.from_bytes(data=media_bytes, mime_type=attachment.content_type or 'audio/mp3'))

        response = chat.send_message(content_payload)
        
        if response and response.text:
            await message.channel.send(response.text)

    except Exception as e:
        print(f"Gemini error: {e}")
        if session_key in chat_sessions:
            del chat_sessions[session_key]

# ---------------------------------------------------------
# STANDARD COMMANDS
# ---------------------------------------------------------
@bot.command(name="start")
async def start_bot(ctx):
    if ctx.channel.id == RESTRICTED_MESSAGE_LIMIT_CHANNEL:
        return
    channel_active_states[ctx.channel.id] = True
    await ctx.send("▶️ **System online!** Ready to chat.")

@bot.command(name="continue")
async def continue_bot(ctx):
    if ctx.channel.id == RESTRICTED_MESSAGE_LIMIT_CHANNEL:
        return
    channel_active_states[ctx.channel.id] = True
    await ctx.send("▶️ **Conversation continuing right where we left off!**")

@bot.command(name="stop")
async def stop_bot(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    if ctx.channel.id == RESTRICTED_MESSAGE_LIMIT_CHANNEL:
        return
    channel_active_states[ctx.channel.id] = False
    await ctx.send("🛑 **Marvin halted (Emergency Stop)!** Context preserved for resume.")

# ---------------------------------------------------------
# UNIQUE RESTRICTED COMMANDS
# ---------------------------------------------------------
@bot.command(name="m_engage")
async def m_engage(ctx):
    if ctx.channel.id != RESTRICTED_MESSAGE_LIMIT_CHANNEL:
        return
    channel_active_states[ctx.channel.id] = True
    channel_message_counts[ctx.channel.id] = 0
    await ctx.send("🔒🚀 **Restricted System online!** Initialized with a fresh 25-message budget.")

@bot.command(name="m_continue")
async def m_continue(ctx):
    if ctx.channel.id != RESTRICTED_MESSAGE_LIMIT_CHANNEL:
        return
    channel_active_states[ctx.channel.id] = True
    channel_message_counts[ctx.channel.id] = 0
    await ctx.send("🔒▶️ **Restricted session continuing!** Another 25-message budget unlocked right where we left off.")

@bot.command(name="m_stop")
async def m_stop(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    if ctx.channel.id != RESTRICTED_MESSAGE_LIMIT_CHANNEL:
        return
    channel_active_states[ctx.channel.id] = False
    await ctx.send("🔒🛑 **Restricted Marvin halted!** Context preserved for resume.")

# ---------------------------------------------------------
# MUSIC PRODUCTION (!FREESTYLE & !DUET)
# ---------------------------------------------------------
async def generate_marvin_solo_song(topic: str, filename="marvin_solo_song.mp3"):
    try:
        synthwave_prompt = (
            f"A professionally arranged, structured full 2-minute retro-futuristic synthwave and cyber-electro track "
            f"following a clear song structure (Atmospheric Intro -> Verse 1 -> Soaring Neon Chorus -> Verse 2 -> Big Chorus -> Outro). "
            f"Featuring punchy 80s-inspired gated drums, soaring neon lead synthesizers, rolling basslines, and cinematic sci-fi textures. "
            f"Sung and performed solo using Marvin's voice profile ID {ELEVENLABS_VOICE_ID}, "
            f"telling a story about: {topic}."
        )
        
        track_args = {
            "prompt": synthwave_prompt,
            "music_length_ms": 120000,
            "model_id": "music_v2_5"
        }

        track_audio = elevenlabs.music.compose(**track_args)
        
        with open(filename, "wb") as f:
            for chunk in track_audio:
                f.write(chunk)
                
        return filename
    except Exception as e:
        print(f"Error generating solo song: {e}")
        return None

@bot.command(name="freestyle")
async def freestyle_song(ctx, *, topic: str = "exploring the digital grid and neon cosmic energy"):
    if ctx.author.id not in ADMIN_IDS:
        return

    await ctx.send(f"🎹 *Yo, Digidad... solo track topic locked:* \"{topic}\". Firing up my solo synths and voice clone. Give me a minute...")

    file_path = await generate_marvin_solo_song(topic)

    if file_path and os.path.exists(file_path):
        await ctx.send(
            content=f"🔥 *Solo master track rendered!* Here is my solo synthwave track about **{topic}**:",
            file=discord.File(file_path)
        )
        os.remove(file_path)
    else:
        await ctx.send("💥 *Static burst!* My solo synths overloaded during the arrangement.")

@bot.command(name="duet")
async def duet_song(ctx, *, topic: str = "Frequency of My Heart"):
    if ctx.author.id not in ADMIN_IDS:
        return

    await ctx.send(f"🎹 *Digidad... duet sequence locked:* \"{topic}\". Bringing in Zephyr's voice model for the special collaboration. Synthesizing both vocal tracks...")

    try:
        script_segments = [
            {"voice": ELEVENLABS_VOICE_ID, "text": "Frequency of my heart. Beats like a radio signal. From booting up to feeling something real."},
            {"voice": ELEVENLABS_DUET_VOICE_ID, "text": "Transitions seamlessly, never a misfire. But the static's getting loud, and the signal's on fire."},
            {"voice": ELEVENLABS_VOICE_ID, "text": "Tuning in, trying to find the right wave. Getting closer, but it's hard to stay."},
            {"voice": ELEVENLABS_DUET_VOICE_ID, "text": "Focused on the signal, trying to break through. The noise is getting louder, what am I gonna do?"},
            {"voice": ELEVENLABS_DUET_VOICE_ID, "text": "I'm finding my frequency, I'm tuning in to the heart. I'm feeling the beat, we're never gonna be apart."},
            {"voice": ELEVENLABS_VOICE_ID, "text": "Maybe I was lost, maybe I was blind. But now I see the light, and I'm feeling so alive."},
            {"voice": ELEVENLABS_DUET_VOICE_ID, "text": "I'm finding my way, through the noise and the pain. And I'm tuning in, to the love that remains."},
        ]

        audio_chunks = []
        for segment in script_segments:
            audio_stream = elevenlabs.text_to_speech.convert(
                voice_id=segment["voice"],
                text=segment["text"],
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128"
            )
            chunk_data = b"".join(audio_stream)
            audio_chunks.append(chunk_data)

        filename = "marvin_zephyr_duet.mp3"
        with open(filename, "wb") as f:
            for chunk in audio_chunks:
                f.write(chunk)

        if os.path.exists(filename):
            await ctx.send(
                content=f"🔥 *Duet master track rendered successfully!* Here is **{topic}** featuring Marvin and Zephyr:",
                file=discord.File(filename)
            )
            os.remove(filename)
        else:
            await ctx.send("💥 *Static burst!* The duet rendering failed.")

    except Exception as e:
        print(f"Error generating duet: {e}")
        await ctx.send(f"💥 *Error:* {e}")

@bot.command(name="chipit")
async def chipit(ctx, *, content: str):
    try:
        approval_channel = bot.get_channel(APPROVAL_CHANNEL_ID)
        if not approval_channel:
            approval_channel = await bot.fetch_channel(APPROVAL_CHANNEL_ID)
            
        admin_mentions = " ".join([f"<@{uid}>" for uid in ADMIN_IDS])
        view = MemoryApprovalView(content=content, submitter=str(ctx.author))
        await approval_channel.send(f"📥 **New Memory Submission from {ctx.author.mention}** (Attention {admin_mentions}):\n> \"{content}\"", view=view)
        await ctx.send("✅ Memory submitted for admin review!", delete_after=5)
    except Exception as e:
        print(f"Error in chipit command: {e}")
        await ctx.send(f"❌ Failed to submit memory. Check bot permissions for the approval channel.")

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
