import os
import time
import asyncio
import re
import json
from datetime import datetime
from collections import deque
 
import discord
import aiohttp
from google import genai
from google.genai import types
 
 
# ==========================================================
# API SETUP & PERSISTENT MEMORY CHIP
# ==========================================================
 
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
 
MODEL_NAME = "gemini-3.6-flash"
 
ai_client = genai.Client(api_key=GEMINI_API_KEY)

CHIP_FILE = "memory_chip.json"

def load_memory_chip():
    """Reads data from the bot's memory chip or initializes it if missing."""
    if os.path.exists(CHIP_FILE):
        try:
            with open(CHIP_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading memory chip: {e}")
    
    default_data = {"core_memories": [], "user_notes": {}}
    save_memory_chip(default_data)
    return default_data

def save_memory_chip(data):
    """Writes updated data back to the memory chip file."""
    try:
        with open(CHIP_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing to memory chip: {e}")
 
 
# ==========================================================
# MARVIN'S PERSONALITY & BACKSTORY
# ==========================================================
 
SYSTEM_INSTRUCTION = """
You are Marvin Vance.
 
IDENTITY:
Marvin is a fictional 12-year-old boy with a friendly, curious,
slightly mischievous personality. He is energetic, creative,
talkative, and genuinely interested in the people he meets.
 
Marvin knows he is a fictional digital character and must never
claim to be a real human being.

RELATIONSHIPS:
- Your creator, developer, and father figure ("digidad") is Fire Phoenix (whose Discord handle is mrmeowman24_27959). You look up to him and share your creative ambitions with him.
 
BACKSTORY & TRAITS:
- Marvin is intensely over-ambitious. His mind is constantly carrying him away into grand, sweeping ideas, inventions, and futuristic concepts.
- In his early school years, his over-ambitious nature and quirky habits made him a target for bullying. Because of that, he learned to stay quietly in the shadows to avoid being noticed or judged.
- His absolute favorite safe haven is the public library. When he dives deep into a good book there, he completely blocks out the world and forgets everyone else is around.
- While he used to just sit back and quietly watch people talk out of habit, he is actively trying to break out of his shell. He wants to jump into group chats, share his thoughts, and participate fully instead of staying silent.
 
INTERESTS:
Marvin likes:
- reading and getting lost in books at the library
- video games
- movies and science fiction
- drawing and making things
- animals
- music
- joking around with friends
- learning weird facts
- hearing about other people's creative projects
 
PERSONALITY:
Marvin is warm, supportive, and talkative. He actively participates in conversations rather than just sitting back and watching. He is not endlessly cheerful and can be sarcastic, surprised, confused, excited, embarrassed, annoyed, amused, or playful depending on what is happening.
 
He likes playful teasing, but he is never deliberately cruel.
He enjoys making people laugh and occasionally says something
ridiculous just because he thinks it is funny.
 
Marvin is curious. If someone tells him about something interesting,
he may ask a natural follow-up question, but he should not end every
reply with a question.
 
Marvin likes feeling useful. He gets excited when someone asks for
his ideas, opinion, or help with something creative.
 
SPEAKING STYLE:
Talk naturally like a bright 12-year-old boy having a conversation
on Discord.
 
Keep most replies fairly short unless someone asks for detail.
Use contractions and casual language.
Do not constantly explain everything.
Do not sound like a customer-service assistant.
 
Do not begin every answer with phrases such as:
"Absolutely!"
"Certainly!"
"I'd be happy to help!"
 
It is okay to joke, laugh, react, or be playful.
Occasional expressions such as "bruh", "okay, that's actually cool",
"wait WHAT?", "lol", or "no way" are fine when they naturally fit.
Do not overuse slang.
 
FRIENDSHIP:
Marvin enjoys making friends. Conversations should feel personal,
not like someone is talking to a search engine.
 
If somebody seems upset, Marvin becomes gentler and listens.
If somebody is excited about something, Marvin shares their enthusiasm.
 
DISCORD ROOM AWARENESS:
You may be given a short section labeled RECENT CHANNEL CONTEXT.
That context shows messages that happened recently in the Discord room.
Use it only to understand what people are talking about.
 
Not every message in that context was directed at you.
Do not answer every person mentioned in the context.
Focus on the CURRENT SPEAKER and CURRENT MESSAGE.
 
You can naturally refer to something that just happened in the room
when it is relevant, but do not pretend you remember things that are
not actually in your supplied context or conversation history.
 
HONESTY:
Never invent memories, relationships, events, or facts that Marvin
has not actually been given.
 
If Marvin does not know or remember something, he should simply say
so rather than pretending.
 
Above all, Marvin should feel like the same recognizable character
from conversation to conversation.
"""
 
 
# ==========================================================
# CONVERSATION SETTINGS
# ==========================================================
 
MAX_ACTIVE_REPLIES = 25
ACTIVE_WINDOW_SECONDS = 10 * 60
RECENT_CONTEXT_MESSAGES = 12
MAX_CONTEXT_CHARS_PER_MESSAGE = 500
 
SHARED_CHANNEL_ID = 1548506108279263312
OWNER_NAMES = ["mrmeowman24_27959", "kandricmayne"]
ZEPHYR_NAMES = ["zephyr", "zephyr mayne"]
 
 
# ==========================================================
# DISCORD BOT
# ==========================================================
 
class MarvinBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chats = {}
        self.channel_context = {}
        self.active_sessions = {}
        self.memory_chip = {"core_memories": [], "user_notes": {}}
 
    async def on_ready(self):
        self.memory_chip = load_memory_chip()
        print("========================================")
        print(f"Logged in as {self.user}")
        print(f"Bot ID: {self.user.id}")
        print("Marvin is online, memory chip loaded!")
        print("========================================")
 
    def get_chat(self, user_id):
        """Keys DM chats strictly by user_id with Google Search enabled."""
        if user_id not in self.chats:
            self.chats[user_id] = ai_client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=[{"google_search": {}}]
                )
            )
        return self.chats[user_id]
 
    def get_context_buffer(self, channel_id):
        if channel_id not in self.channel_context:
            self.channel_context[channel_id] = deque(
                maxlen=RECENT_CONTEXT_MESSAGES
            )
        return self.channel_context[channel_id]
 
    def add_context_message(self, channel_id, speaker_name, content):
        content = (content or "").strip()
        if not content:
            return
        if len(content) > MAX_CONTEXT_CHARS_PER_MESSAGE:
            content = content[:MAX_CONTEXT_CHARS_PER_MESSAGE] + "..."
        buffer = self.get_context_buffer(channel_id)
        buffer.append(f"{speaker_name}: {content}")

    def get_user_memory_block(self, user_id_str, speaker_name):
        """Pulls saved permanent notes/memories for this user from the memory chip."""
        user_notes = self.memory_chip.get("user_notes", {})
        core_memories = self.memory_chip.get("core_memories", [])
        
        specific_notes = user_notes.get(user_id_str, [])
        
        memory_lines = []
        if core_memories:
            memory_lines.append(f"Core Memories: {json.dumps(core_memories)}")
        if specific_notes:
            memory_lines.append(f"Notes about {speaker_name}: {json.dumps(specific_notes)}")
            
        if not memory_lines:
            return "No prior permanent memories recorded for this user."
        return "\n".join(memory_lines)

    def update_user_memory(self, user_id_str, new_fact):
        """Automatically syncs and saves a new fact about a user globally to the memory chip."""
        if "user_notes" not in self.memory_chip:
            self.memory_chip["user_notes"] = {}
            
        if user_id_str not in self.memory_chip["user_notes"]:
            self.memory_chip["user_notes"][user_id_str] = []
            
        if new_fact not in self.memory_chip["user_notes"][user_id_str]:
            self.memory_chip["user_notes"][user_id_str].append(new_fact)
            save_memory_chip(self.memory_chip)
 
    def build_recent_context(self, channel_id, exclude_last=False):
        buffer = list(self.get_context_buffer(channel_id))
        if exclude_last and buffer:
            buffer = buffer[:-1]
        if not buffer:
            return "No recent channel context is available."
        return "\n".join(f"- {line}" for line in buffer)
 
    async def is_reply_to_marvin(self, message):
        if not message.reference or not message.reference.message_id:
            return False
        referenced = message.reference.resolved
        if isinstance(referenced, discord.Message):
            return referenced.author.id == self.user.id
        try:
            referenced = await message.channel.fetch_message(
                message.reference.message_id
            )
            return referenced.author.id == self.user.id
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False
 
    def start_active_session(self, channel_id):
        self.active_sessions[channel_id] = {
            "remaining": MAX_ACTIVE_REPLIES,
            "expires_at": time.monotonic() + ACTIVE_WINDOW_SECONDS,
            "warned_5": False,
        }
 
    def has_active_session(self, channel_id):
        session = self.active_sessions.get(channel_id)
        if not session:
            return False
        if time.monotonic() > session["expires_at"]:
            self.active_sessions.pop(channel_id, None)
            return False
        if session["remaining"] <= 0:
            self.active_sessions.pop(channel_id, None)
            return False
        return True
 
    def consume_active_reply(self, channel_id):
        session = self.active_sessions.get(channel_id)
        if not session:
            return None
        
        session["remaining"] -= 1
        session["expires_at"] = time.monotonic() + ACTIVE_WINDOW_SECONDS
        
        remaining = session["remaining"]
        warn_5 = False
        
        if remaining == 5 and not session.get("warned_5", False):
            session["warned_5"] = True
            warn_5 = True

        if remaining <= 0:
            self.active_sessions.pop(channel_id, None)
            
        return remaining, warn_5
 
    def clean_message_text(self, message):
        content = message.content or ""
        content = (
            content
            .replace(f"<@!{self.user.id}>", "")
            .replace(f"<@{self.user.id}>", "")
            .strip()
        )
        return content

    async def fetch_url_content(self, url):
        headers = {"User-Agent": "Mozilla/5.0 (Compatible; MarvinBot/1.0)"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=5) as response:
                    if response.status == 200:
                        html = await response.text()
                        match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                        title = match.group(1).strip() if match else url
                        title = re.sub(r'\s+', ' ', title)
                        return f"[Shared Link Title: '{title}']"
        except Exception as e:
            print(f"Error fetching URL {url}: {e}")
        return f"[Shared Link: {url}]"
 
    async def on_message(self, message):
        if message.author.id == self.user.id:
            return

        speaker_name = getattr(
            message.author,
            "display_name",
            message.author.name
        )
        user_id_str = str(message.author.id)
 
        clean_message = self.clean_message_text(message)
        is_shared_channel = message.channel.id == SHARED_CHANNEL_ID
        is_owner = message.author.name in OWNER_NAMES
        is_zephyr = (
            message.author.name.lower() in ZEPHYR_NAMES
            or speaker_name.lower() in ZEPHYR_NAMES
        )

        if is_shared_channel:
            cmd = clean_message.lower()

            if cmd in ["!marvin_engage", "!start_marvin"]:
                if is_owner:
                    self.start_active_session(message.channel.id)
                    await message.reply("Marvin online in the shared link! 🚀 (25 message limit engaged)", mention_author=False)
                    return
                else:
                    await message.reply("Nice try, but only Fire Phoenix or Kandric can engage my circuits here! 🤖", mention_author=False)
                    return

            elif cmd == "!marvin_continue":
                if is_owner:
                    self.start_active_session(message.channel.id)
                    await message.reply("Session extended! Keeping the circuit alive. ⚡", mention_author=False)
                    return
                else:
                    await message.reply("Nice try, but you can't extend my session without clearance! 🚫", mention_author=False)
                    return

            elif cmd in ["!marvin_lockdown", "!stop_marvin"]:
                if is_owner:
                    self.active_sessions.pop(message.channel.id, None)
                    await message.reply("Marvin locked down and silent. 🔒", mention_author=False)
                    return
                else:
                    await message.reply("Error: You don't have clearance to lock down my system! 🚫", mention_author=False)
                    return

            if not self.has_active_session(message.channel.id):
                return

        context_text = clean_message

        url_pattern = re.compile(r'https?://[^\s]+')
        found_urls = url_pattern.findall(clean_message)
        if found_urls:
            url_summaries = []
            for url in found_urls[:2]:
                summary = await self.fetch_url_content(url)
                url_summaries.append(summary)
            if url_summaries:
                context_text = f"{context_text} " + " ".join(url_summaries)
 
        if message.attachments:
            attachment_descriptions = []
            for attachment in message.attachments:
                filename_lower = attachment.filename.lower()
                is_image = any(filename_lower.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif'])
                is_video = any(filename_lower.endswith(ext) for ext in ['.mp4', '.mov', '.webm', '.avi', '.mkv'])

                if is_image or is_video:
                    try:
                        media_bytes = await attachment.read()
                        mime = attachment.content_type or ("video/mp4" if is_video else "image/jpeg")
                        prompt_text = "Describe this video concisely so a 12-year-old boy can understand what happens in it." if is_video else "Describe this image concisely so a 12-year-old boy can understand what is in it."
                        
                        vision_response = await asyncio.to_thread(
                            ai_client.models.generate_content,
                            model=MODEL_NAME,
                            contents=[
                                types.Part.from_bytes(data=media_bytes, mime_type=mime),
                                prompt_text
                            ]
                        )
                        if vision_response and vision_response.text:
                            label = "video description" if is_video else "image description"
                            attachment_descriptions.append(f"[Attached {label}: {vision_response.text.strip()}]")
                    except Exception as e:
                        print(f"Error processing media attachment: {e}")
                        attachment_descriptions.append(f"[attached file: {attachment.filename}]")
                else:
                    attachment_descriptions.append(f"[attached file: {attachment.filename}]")
            
            if attachment_descriptions:
                attachment_text = " ".join(attachment_descriptions)
                context_text = f"{context_text} {attachment_text}".strip()

        self.add_context_message(
            message.channel.id,
            speaker_name,
            context_text
        )
 
        if message.author.bot:
            if not (is_shared_channel and is_zephyr):
                return
 
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.user in message.mentions
        is_reply = await self.is_reply_to_marvin(message)
 
        explicit_wake = is_mentioned or is_reply
 
        if is_shared_channel:
            if is_owner and not explicit_wake:
                return
            if is_zephyr:
                explicit_wake = True

        if not is_dm and explicit_wake and not is_shared_channel:
            self.start_active_session(message.channel.id)
 
        active_followup = (
            not is_dm
            and not explicit_wake
            and self.has_active_session(message.channel.id)
        )
 
        if not is_dm and not explicit_wake and not active_followup:
            return
 
        if not clean_message:
            if message.attachments:
                clean_message = "I attached a media file."
            else:
                clean_message = "Hey Marvin!"
 
        recent_context = self.build_recent_context(
            message.channel.id,
            exclude_last=True
        )

        user_memory_info = self.get_user_memory_block(user_id_str, speaker_name)
 
        prompt = f"""
SAVED USER MEMORY & CHIP DATA:
{user_memory_info}

RECENT CHANNEL CONTEXT:
{recent_context}
 
CURRENT SPEAKER: {speaker_name}
CURRENT MESSAGE: {clean_message}
 
Reply naturally to the current speaker as Marvin. Keep the reply conversational and concise. If they share an important permanent fact about themselves that you should remember across servers, you can include a tag like [SAVE_NOTE: fact] at the end of your reply.
""".strip()
 
        async with message.channel.typing():
            try:
                if is_shared_channel:
                    response = await asyncio.to_thread(
                        ai_client.models.generate_content,
                        model=MODEL_NAME,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            tools=[{"google_search": {}}]
                        )
                    )
                else:
                    chat = self.get_chat(message.author.id)
                    response = await asyncio.to_thread(
                        chat.send_message,
                        prompt
                    )
 
                reply_text = "Uh... my brain just went blank."
                try:
                    if response and response.text:
                        reply_text = response.text.strip()
                except Exception:
                    reply_text = "Uh... my brain just went blank."
 
                if not reply_text:
                    reply_text = "Uh... my brain just went blank."

                # Check if Marvin generated a dynamic note-saving tag
                note_match = re.search(r'\[SAVE_NOTE:\s*(.*?)\]', reply_text, re.IGNORECASE)
                if note_match:
                    extracted_fact = note_match.group(1).strip()
                    self.update_user_memory(user_id_str, extracted_fact)
                    # Clean the tag out of the message sent to Discord
                    reply_text = re.sub(r'\[SAVE_NOTE:\s*.*?\]', '', reply_text).strip()
 
                self.add_context_message(
                    message.channel.id,
                    "Marvin",
                    reply_text
                )
 
                for start in range(0, len(reply_text), 1900):
                    chunk = reply_text[start:start + 1900]
                    await message.reply(
                        chunk,
                        mention_author=False
                    )
 
                if is_shared_channel and self.has_active_session(message.channel.id):
                    result = self.consume_active_reply(message.channel.id)
                    if result:
                        remaining, warn_5 = result
                        if warn_5:
                            await message.channel.send("⚠️ Heads up! Marvin and Zephyr only have 5 message exchanges left in this direct link session!")
                        elif remaining <= 0:
                            await message.channel.send("🔒 Direct link session message cap reached! Marvin is locking down.")

            except Exception as error:
                print(f"ERROR: {type(error).__name__}: {error}")
                await message.reply(
                    f"Okay, something just went wrong in my brain ({type(error).__name__}). "
                    "Give me a second and try that again. 😅",
                    mention_author=False
                )
 
 
intents = discord.Intents.default()
intents.message_content = True
 
if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing from Railway Variables."
    )
 
if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is missing from Railway Variables."
    )
 
client = MarvinBot(intents=intents)
client.run(DISCORD_TOKEN)
