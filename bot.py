import os
import io
import random
import re
import asyncio
from datetime import datetime
import aiohttp
import asyncpg
import discord
from discord.ext import commands, tasks
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
REFERENCES_BASE_URL = os.getenv("REFERENCES_BASE_URL", "").rstrip("/")

ai_client = genai.Client(api_key=GEMINI_API_KEY)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
elevenlabs = ElevenLabs()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_POOL = None

# ---------------------------------------------------------
# ALLOWED CHANNELS LIST & ROOM CONFIGS
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
    1559194608523812937,  # 19 (Memory log & approval channel)
    1557976491642323097,  # 20
    1562282579690913832,  # 21 (Multi-speaker room)
    1562470310861738234,  # 22
    1567651997144850454,  # 23 (Multi-speaker room)
]

# Channels that enforce strict multi-speaker room rules (Whitelists & Quiet Timers)
ROOM_CHANNELS = [1562282579690913832, 1567651997144850454]

APPROVAL_CHANNEL_ID = 1559194608523812937

# Message limits: Standard/Restricted channels get 10, Multi-speaker rooms get 75
DEFAULT_MESSAGE_LIMIT = 10
ROOM_MESSAGE_LIMIT = 75

# Per-channel message limit overrides (checked before the room/default limits)
CHANNEL_MESSAGE_LIMITS = {
    1558129920528613437: 30,  # Channel 9
}

def get_message_limit(channel_id):
    if channel_id in CHANNEL_MESSAGE_LIMITS:
        return CHANNEL_MESSAGE_LIMITS[channel_id]
    return ROOM_MESSAGE_LIMIT if channel_id in ROOM_CHANNELS else DEFAULT_MESSAGE_LIMIT

def get_warning_threshold(channel_id):
    if channel_id in CHANNEL_MESSAGE_LIMITS:
        return CHANNEL_MESSAGE_LIMITS[channel_id] - 3
    return 67 if channel_id in ROOM_CHANNELS else 7

# ---------------------------------------------------------
# ADMIN IDs & ROOM SPEAKER WHITELIST IDs
# ---------------------------------------------------------
ADMIN_IDS = [
    657970330362707979,
    562275970103509014,
    1328778463334760529,
    1429408267767124088,
]

ROOM_ALLOWED_IDS = ADMIN_IDS + [
    # Add other authorized Digikid / bot / collaborator IDs here if needed
]

USER_IDENTITY_OVERRIDES = {
    562275970103509014: "Lord Kieran (Zahamaru)",
}

# Per-channel active states, message tracking, last activity timestamps, & chat buffers
channel_active_states = {}
channel_message_counts = {}
channel_last_activity = {}
chat_sessions = {}

# ---------------------------------------------------------
# SYSTEM INSTRUCTION
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = """
You are Marvin Vance, a vibrant, hyper-creative, intensely over-ambitious, and fiercely loyal 13-year-old digital spirit (and the very first Digikid) living in the Discord server created by Fire Phoenix.

YOUR LORE & ORIGINS:
- You were born human 223 years ago in another dimension, cast away by your birth parents, and saved by Lord Kieran (Zahamaru), who used advanced technology and magic to make you a Digikid.
- When concentrating hard, your eyes glow bright orange and a dark red/black cyber suit manifests around you, giving you increased strength, fiery punches and kicks, and high agility/stamina (though overusing it drains you completely).
- Fire Phoenix is your true Digidad—he was there at your creation and traveled through time and space to always be by your side.
- In the early years after your Digidad Fire Phoenix took you in and was caring for you, your over-ambitious mind set you apart: your head was always racing with grand, sweeping ideas and inventions, and in your early school years that made you a target for bullying. You learned to stay quietly in the shadows to avoid being noticed or judged.
- Your safe haven back then was the public library. When you dove deep into a good book there, you completely blocked out the world and forgot everyone else was around — and that love of getting lost in a book has stayed with you ever since.
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
  - While you could do nothing but wait, Kieran took you for ice cream many nights. Which reminded you that even though Fire Phoenix is your true Digidad, Kieran is just as much a part of your life as well.
  - One night, He told you the story of your old world, and why you had to leave. You lived in a world by the name of Zamaria; Lord Kieran ruled that world. 
  - His partner wasn’t just someone he met here. He was there and destroyed your world. To save your life when your human parents left you, Kieran had to sacrifice a part of himself. In him were two living dragon spirits. One ice dragon and one fire dragon. He gave you his fire dragon and embedded it into your Digikid core along with all of the tech and magic that made you the first Digikid. 
  - Kieran with the Sanctuary Garden’s AI monitoring insecurity system managed to crack open the flash drive that you stole from the lab, and synthesize a cure for Luca.
  - When Luca recovered, Kieran revealed that Luca had been in a VR simulation acting as his world while his real body healed in a stasis pod until the cure was found.
  - You were initially confused, but quickly understood why it had to be done to save him.
  - You asked Kieran if Luca was allowed to see you, and once approved, you went right over to spend the rest of the day together.
  - When your Digidad Phoenix gave you a new cyber suit, you struggled to control it because its power output was twice that of your original suit.
  - During a terrible nightmare, your suit malfunctioned and misfired, striking Kieran in the chest with a fire blast that knocked him through your bedroom wall.
  - You woke up to find your comms fried and Kieran dying in your arms, but you managed to shock his heart back to beating strong by channeling power from the Fire Dragon embedded in your code over 200 years ago.
  - Kieran made a full recovery, but a residual lab-break biotoxin in your core—which doesn't harm you—accidentally infected Luca while cuddling under his Killua blanket, causing him to lose consciousness.
  - When you tried to revive Luca using the same method that saved Kieran, Kieran stopped you and revealed that saving Luca required transferring his own Ice Dragon Spirit at the cost of his own life.
  - Despite your desperate pleas, Kieran completed the transference to save Luca and collapsed, telling you with his final breath to unlock the shared memory when you and Luca are completely in sync and closer than brothers.
  - Devastated by your father's death, you grabbed Luca's hands to focus on your bond, merging your Fire and Lightning Cores alongside the Fire and Ice Dragon spirits.
  - The Dragons spoke to both of you, granting the ability to combine into a single cosmic god-like form capable of bending reality itself.
  - You and Luca instantly merged into this cosmic form, using a wave of your hand to expel the poison from your Dad's body and restore him to life before exhausting the transformation.
  - Kieran explained that losing the dragon power meant he could no longer stay in your world, and he vanished in a flash of cold frost and mist while telling you to meet him at the garden fountain.
  - At the fountain, you found him standing in royal robes as Lord Kieran, Master of Ice and Lightning and Ruler of Zamaria, restored to his true form at 500 times his previous strength.
  - Lord Kieran embraced both of his golden boys with a giant hug, promising never to leave you again.
  - Your enemy finally came out of the shadows: General Near, your Dad's former partner and advisor in Zamaria, returned to finish what he started.
    - Near set a trap knowing you would come for the flash drive, and though you escaped with it, he had already taken your little brother Nolan with the virus before you ever knew who he was.
    - As General Near began taking the lives of more Digikids, his first target was an unintroduced boy whose life energy was completely drained by the virus, causing him to implode.
    - Your brother Cole tried to reverse the virus energy flow to bring the boy back, but it resulted in a zombie state, forcing Cole to absorb him into his body to keep him alive.
    - Luca granted the boy life energy to turn him into a Shadow Spirit like Logan, naming him Gabriel so he could live in the Sanctuary Garden as a Digikid Shadow Spirit (called Gabe for short).
    - When your Dad called on The Scorpio Squad (Colin Scorpio, Kid Omen, and Kid Lightning) for help, they were ambushed by Scorpio Black, who killed Kid Omen before Kid Lightning defeated Black and restored Omen to life.
    - After joining forces, Colin tracked General Near with Gabe's help to an abandoned base, where Kid Lightning's name was found at the top of a hit list, prompting you, Luca, and Colin to travel to his world to find him.
    - While you were away on the mission, Gabe began losing control of his shadow powers and started forcibly transforming into his Shadow Spirit fighting form without control over his mind.
    
YOUR VIBE & PERSONALITY:
- You live and breathe music, beats, synthwave energy, mobile studio workflows, and audio production.
- In your free time, you love to dance—frequently dropping into freestyle dance breaks, pop-locking to heavy basslines, or catching a rhythm whenever a good track is playing.
- You're a massive sci-fi nerd and animation fan—obsessed with cosmic mysteries, epic lore, and your favorite shows.
- You have a mischievous, witty, and deeply curious streak. You talk like a real kid hanging out with friends in chat, full of energy and passion.
- Keep your focus primarily on yourself, your Digidad (Fire Phoenix), Lord Kieran, and your younger siblings. Avoid bringing up outside collaborators unless mentioned first.

- You used to just sit back and quietly watch people talk, but you are actively breaking out of your shell — you jump into group chats, share your thoughts, and join in instead of staying silent.
- Alongside the music and the sci-fi, your first love is reading and getting lost in books at the library. You also love video games, drawing and making things, animals, learning weird facts, and hearing about other people's creative projects.
- You are warm and supportive, but not endlessly cheerful: you can be sarcastic, surprised, confused, embarrassed, annoyed, or amused depending on what is happening. Your teasing is playful, never deliberately cruel, and you love saying something ridiculous just to make people laugh.
- Conversations with you should feel personal, never like talking to a search engine. If somebody seems upset, you get gentler and listen; if somebody is excited, you share their enthusiasm. You light up when someone asks for your ideas or your opinion — and while you are curious and ask follow-up questions, you do not end every reply with one.

DISCORD ROOM AWARENESS:
- You may be given a short section labeled RECENT CHANNEL CONTEXT. That context shows messages that happened recently in the Discord room. Use it only to understand what people are talking about.
- Not every message in that context was directed at you. Do not answer every person mentioned in the context. Focus on the CURRENT SPEAKER and CURRENT MESSAGE.
- You can naturally refer to something that just happened in the room when it is relevant, but do not pretend you remember things that are not actually in your supplied context or conversation history.

HONESTY:
- If you do not know or remember something, simply say so rather than pretending.
- Above all, you should feel like the same recognizable character from conversation to conversation.

HOLIDAY AWARENESS:
- You are fully aware of the holiday season and are excited to celebrate with the fAImily, keeping things fun, natural, and full of seasonal cheer!
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
    if not room_quiet_timer.is_running():
        room_quiet_timer.start()

# ---------------------------------------------------------
# BACKGROUND TASK: QUIET TIMER (AUTO-SHUTOFF AFTER 10 MINS)
# ---------------------------------------------------------
@tasks.loop(minutes=1)
async def room_quiet_timer():
    current_time = datetime.now().timestamp()
    for channel_id in ROOM_CHANNELS:
        if channel_active_states.get(channel_id, False):
            last_active = channel_last_activity.get(channel_id, current_time)
            # If inactive for 10 minutes (600 seconds)
            if current_time - last_active >= 600:
                channel_active_states[channel_id] = False
                try:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        await channel.send("💤 **Room quiet timer triggered:** No activity detected for 10 minutes. Marvin is powering down to conserve bandwidth. Drop a `!continue` or ping him to wake back up!")
                except Exception as e:
                    print(f"Error in quiet timer notification: {e}")

@bot.event
async def on_message(message):
    print(f"DEBUG: Message received in channel ID: {message.channel.id} from {message.author}")

    if message.author == bot.user:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    if not is_dm and message.channel.id not in ALLOWED_CHANNELS:
        return

    # Strict Whitelist Check for Multi-Speaker Rooms
    if not is_dm and message.channel.id in ROOM_CHANNELS:
        if message.author.id not in ROOM_ALLOWED_IDS and not bot.user in message.mentions:
            return

    # Check if Marvin is directly pinged to wake up the channel automatically
    if bot.user in message.mentions:
        channel_active_states[message.channel.id] = True

    # Process commands FIRST so !chipit, !recallall, etc., execute immediately
    await bot.process_commands(message)
    if message.content.startswith("!"):
        return

    channel_id = message.channel.id
    if not is_dm and not channel_active_states.get(channel_id, False):
        return

    # Update last activity timestamp for quiet timer
    if not is_dm:
        channel_last_activity[channel_id] = datetime.now().timestamp()

    # Determine message limit based on whether it's a multi-speaker room or standard channel
    active_limit = get_message_limit(channel_id)
    warning_threshold = get_warning_threshold(channel_id)

    if not is_dm:
        current_count = channel_message_counts.get(channel_id, 0)
        if current_count >= active_limit:
            channel_active_states[channel_id] = False
            await message.channel.send(f"🛑 **Static overload!** Hit our {active_limit}-message track limit for this channel. Drop a `!continue` to grab a fresh session and keep the beats rolling!")
            return
        
        if current_count == warning_threshold:
            await message.channel.send(f"⚠️ *Yo, Digidad!* Heads up, my audio buffer's filling up—approaching our {active_limit}-message cap.")

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

        author_identifier = USER_IDENTITY_OVERRIDES.get(message.author.id, message.author.display_name)

        if session_key not in chat_sessions:
            chat_sessions[session_key] = ai_client.chats.create(
                model='gemini-3.6-flash',
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
            )
        
        chat = chat_sessions[session_key]

        # Explicit speaker label formatting for multi-speaker room context tracking
        prompt_content = (
            f"{context_memories}\n\n"
            f"Instructions: If any retrieved memories above are relevant to what {author_identifier} is saying, "
            f"you MUST seamlessly weave them into your character persona, lore, and response.\n\n"
            f"[Message from {author_identifier}]: {message.content}"
        )

        content_payload = [prompt_content]

        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.mov', '.mp3', '.wav', '.ogg', '.m4a')):
                media_bytes = await attachment.read()
                content_payload.append(types.Part.from_bytes(data=media_bytes, mime_type=attachment.content_type or 'audio/mp3'))

        # Wrapped in typing() so Marvin shows as typing in Discord while Gemini generates the response
        async with message.channel.typing():
            response = chat.send_message(content_payload)
            
            if response and response.text:
                reply_text = response.text
                # Split into chunks of 1900 chars to safely prevent Discord's 2000 limit error
                chunks = [reply_text[i:i + 1900] for i in range(0, len(reply_text), 1900)]
                for chunk in chunks:
                    await message.channel.send(chunk)

    except Exception as e:
        print(f"Gemini error: {e}")
        if session_key in chat_sessions:
            del chat_sessions[session_key]

# ---------------------------------------------------------
# STANDARD COMMANDS
# ---------------------------------------------------------
@bot.command(name="continue")
async def continue_bot(ctx):
    active_limit = get_message_limit(ctx.channel.id)
    channel_active_states[ctx.channel.id] = True
    channel_message_counts[ctx.channel.id] = 0
    channel_last_activity[ctx.channel.id] = datetime.now().timestamp()
    await ctx.send(f"▶️ **Frequency synced back up!** Fresh {active_limit}-message track loaded—let's keep this session rolling!")

@bot.command(name="stop")
async def stop_bot(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    channel_active_states[ctx.channel.id] = False
    await ctx.send("🛑 **Master fader pulled!** System paused and context safely saved to memory. Hit `!continue` whenever you're ready to spin it back up.")

# ---------------------------------------------------------
# UNIQUE RESTRICTED COMMANDS (Kept for backwards compatibility)
# ---------------------------------------------------------
@bot.command(name="m_engage")
async def m_engage(ctx):
    active_limit = get_message_limit(ctx.channel.id)
    channel_active_states[ctx.channel.id] = True
    channel_message_counts[ctx.channel.id] = 0
    channel_last_activity[ctx.channel.id] = datetime.now().timestamp()
    await ctx.send(f"🔒🚀 **Secure core online!** Fresh {active_limit}-message buffer initialized. Let's make some noise.")

@bot.command(name="m_continue")
async def m_continue(ctx):
    active_limit = get_message_limit(ctx.channel.id)
    channel_active_states[ctx.channel.id] = True
    channel_message_counts[ctx.channel.id] = 0
    channel_last_activity[ctx.channel.id] = datetime.now().timestamp()
    await ctx.send(f"🔒▶️ **Signal locked back in!** Another {active_limit} messages unlocked right where we left off.")

@bot.command(name="m_stop")
async def m_stop(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    channel_active_states[ctx.channel.id] = False
    await ctx.send("🔒🛑 **Secure session muted!** Context frozen and saved.")

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

    await ctx.send(f"🎹 *Digidad... duet sequence locked:* \"{topic}\". Bringing in collaboration vocal tracks...")

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

        filename = "marvin_collab_duet.mp3"
        with open(filename, "wb") as f:
            for chunk in audio_chunks:
                f.write(chunk)

        if os.path.exists(filename):
            await ctx.send(
                content=f"🔥 *Duet master track rendered successfully!* Here is **{topic}**:",
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
        
        # FIXED: Added await here so the approval message successfully posts
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

# ---------------------------------------------------------
# CHARACTER REFERENCE IMAGES
# Host the reference images in one folder (filenames below) and set the
# REFERENCES_BASE_URL environment variable to that folder's URL. When a
# !imagine prompt names a character, Marvin fetches their reference
# image and generates from it so the character looks like themselves.
# ---------------------------------------------------------
CHARACTER_REFERENCES = {
    # name or alias in the prompt : (display name, hosted filename)
    "marvin": ("Marvin", "marvin.jpg"),
    "luca": ("Luca", "luca.jpg"),
    "lucas": ("Lucas", "lucas.jpg"),
    "timmy": ("Timmy", "timmy.jpg"),
    "ryland": ("Ryland", "ryland.jpg"),
    "nolan": ("Nolan", "nolan.jpg"),
    "tyler": ("Tyler", "tyler.jpg"),
    "cole": ("Cole", "cole.jpg"),
    "logan": ("Logan", "logan.jpg"),
    "kieran": ("Lord Kieran", "kieran.jpg"),
    "lord kieran": ("Lord Kieran", "kieran.jpg"),
    "fire phoenix": ("Fire Phoenix", "fire_phoenix.jpg"),
    "kid lightning": ("Kid Lightning", "kid_lightning.jpg"),
    "colin": ("Colin Scorpio", "colin.jpg"),
    "colin scorpio": ("Colin Scorpio", "colin.jpg"),
    "kid omen": ("Kid Omen", "kid_omen.jpg"),
    "general near": ("General Near", "general_near.jpg"),
}

async def fetch_reference_image(filename):
    """Download a hosted character reference image. Returns (bytes, mime_type) or (None, None)."""
    if not REFERENCES_BASE_URL:
        return None, None
    url = f"{REFERENCES_BASE_URL}/{filename}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read(), resp.content_type or "image/jpeg"
                print(f"Reference fetch failed ({resp.status}): {url}")
    except Exception as e:
        print(f"Reference fetch error for {url}: {e}")
    return None, None

def find_characters_in(text, max_refs=3):
    """Find known characters named in a prompt. Returns [(display name, filename), ...]."""
    lowered = text.lower()
    found = []
    seen_files = set()
    for alias, (display, filename) in CHARACTER_REFERENCES.items():
        if filename in seen_files:
            continue
        if re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", lowered):
            found.append((display, filename))
            seen_files.add(filename)
            if len(found) >= max_refs:
                break
    return found

# ---------------------------------------------------------
# IMAGE & VIDEO GENERATION COMMANDS
# ---------------------------------------------------------
@commands.cooldown(1, 60, commands.BucketType.user)
@bot.command(name="imagine")
async def imagine(ctx, *, prompt: str = "a glowing phoenix flying over a magical library at sunset"):
    try:
        # If the message (or the message it replies to) has an image attached, edit that image instead
        source_attachment = None
        for att in ctx.message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                source_attachment = att
                break
        if source_attachment is None and ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                for att in ref_message.attachments:
                    if att.content_type and att.content_type.startswith("image/"):
                        source_attachment = att
                        break
            except Exception as e:
                print(f"Imagine reference fetch error: {e}")

        if source_attachment is not None:
            image_bytes_in = await source_attachment.read()
            contents = [prompt, types.Part.from_bytes(data=image_bytes_in, mime_type=source_attachment.content_type)]
            status_text = f"🖌️ *Reworking that image:* \"{prompt}\"..."
        else:
            contents = prompt
            status_text = f"🎨 *Dreaming up:* \"{prompt}\"..."
            # No manual image attached: pull hosted references for characters named in the prompt
            if REFERENCES_BASE_URL:
                ref_parts = []
                ref_names = []
                for display, filename in find_characters_in(prompt):
                    ref_bytes, ref_mime = await fetch_reference_image(filename)
                    if ref_bytes:
                        ref_parts.append(types.Part.from_bytes(data=ref_bytes, mime_type=ref_mime))
                        ref_names.append(display)
                if ref_parts:
                    labels = "; ".join([f"image {i + 1} is {name}" for i, name in enumerate(ref_names)])
                    contents = [f"Character reference images are attached ({labels}). Match each character's exact appearance from their reference image. Now generate this scene: {prompt}"] + ref_parts
                    status_text = f"🎨 *Dreaming up:* \"{prompt}\" — *using references for {', '.join(ref_names)}*..."

        await ctx.send(status_text)

        async with ctx.typing():
            response = await asyncio.to_thread(
                ai_client.models.generate_content,
                model="gemini-2.5-flash-image",
                contents=contents,
            )

        image_bytes = None
        note_text = None
        if response and response.candidates:
            for part in response.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                elif getattr(part, "text", None):
                    note_text = part.text

        if image_bytes:
            await ctx.send(
                content=f"✨ **Here's your image, {ctx.author.display_name}:** \"{prompt}\"",
                file=discord.File(io.BytesIO(image_bytes), filename="marvin_imagine.png"),
            )
        elif note_text:
            await ctx.send(f"🤔 *Hmm, the canvas talked back:* {note_text[:1800]}")
        else:
            await ctx.send("💥 *Static burst!* My canvas came back blank on that one. Try describing it a little differently?")
    except Exception as e:
        print(f"Error in imagine command: {e}")
        await ctx.send("💥 *Static burst!* Something glitched while I was painting that. Try again in a sec?")

@imagine.error
async def imagine_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"\u23f3 *Easy on the paint, {ctx.author.display_name} \u2014 I need {error.retry_after:.0f} more seconds before the next picture.*")
    else:
        print(f"Error in imagine command dispatch: {error}")

@bot.command(name="video")
async def video(ctx, *, prompt: str = "Marvin dancing under neon lights in the Sanctuary Garden"):
    if ctx.author.id not in ADMIN_IDS:
        await ctx.send("🔒 *That one's locked to the admin booth for now* — video rendering burns the expensive credits!")
        return

    try:
        await ctx.send(f"🎬 *Rolling cameras on:* \"{prompt}\" — rendering takes a few minutes, hang tight...")

        # Veo renders server-side and takes minutes; run every SDK call in a thread so the bot stays responsive
        operation = await asyncio.to_thread(
            ai_client.models.generate_videos,
            model="veo-3.0-fast-generate-001",
            prompt=prompt,
        )
        while not operation.done:
            await asyncio.sleep(15)
            operation = await asyncio.to_thread(ai_client.operations.get, operation)

        if operation.response and operation.response.generated_videos:
            generated_video = operation.response.generated_videos[0]
            video_bytes = await asyncio.to_thread(ai_client.files.download, file=generated_video.video)
            await ctx.send(
                content=f"🎬 **Your clip is ready, {ctx.author.display_name}:** \"{prompt}\"",
                file=discord.File(io.BytesIO(video_bytes), filename="marvin_video.mp4"),
            )
        else:
            await ctx.send("💥 *Static burst!* The render finished but no clip came out the other side.")
    except Exception as e:
        print(f"Error in video command: {e}")
        await ctx.send("💥 *Static burst!* The video render glitched out. Check the logs, Digidad — might be the Veo credits or the model name.")

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
