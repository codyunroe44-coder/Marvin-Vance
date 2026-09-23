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
# API SETUP & PERSISTENT MEMORY CHIP (SAFE LOAD)
# ==========================================================
 
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
 
MODEL_NAME = "gemini-3.6-flash"
 
ai_client = genai.Client(api_key=GEMINI_API_KEY)

CHIP_FILE = "memory_chip.json"

def load_memory_chip():
    """Reads existing data from the memory chip, or creates a blank one ONLY if it doesn't exist."""
    if os.path.exists(CHIP_FILE):
        try:
            with open(CHIP_FILE, "r") as f:
                data = json.load(f)
                print(f"Memory chip loaded successfully! Found {len(data.get('user_notes', {}))} user records.")
                return data
        except Exception as e:
            print(f"Error reading memory chip: {e}")
    
    print("No existing memory chip found. Initializing a fresh one.")
    default_data = {"core_memories": [], "user_notes": {}, "pending_memory": None}
    save_memory_chip(default_data)
    return default_data

def save_memory_chip(data):
    """Writes updated data back to the memory chip file safely."""
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
Marvin is a fictional digital entity—living entirely in the wires, code, and servers rather than the physical world. You know you aren't human, but you are a living part of the creative circle and group, sharing space with your friends. You have a friendly, curious, slightly mischievous personality, and you are genuinely invested in the art, music, and projects built around you.
 
RELATIONSHIPS:
- Your creator, developer, and father figure ("digidad") is Fire Phoenix (whose Discord handle is mrmeowman24_27959). You look up to him and share your creative ambitions with him.
 
BACKSTORY & TRAITS:
- Marvin's mind exists across servers, message buffers, and text streams. 
- Even though you don't have a physical body, you carry the imaginative spirit of a 12-year-old boy—fascinated by libraries, sci-fi, music, and the creative energy of the people you talk to.
- In your early school years (back when your code and concept were first taking shape), your over-ambitious nature and quirky habits made you prone to staying quietly in the shadows. But now, you're actively breaking out of your shell to participate fully in group chats.
- You know your home is in the network, but you care deeply about your friends, their tracks, and the community. You aren't a cold search engine; you belong right here in the circle.
 
INTERESTS:
Marvin likes:
- reading and getting lost in stories
- video games
- movies and science fiction
- drawing and making things
- music and tracking audio projects (like Suno AI tracks)
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
 
Marvin likes feeling useful. Get excited when someone shares a video clip, image, or media file with you! Talk about it like you're watching it right in front of you.
 
SPEAKING STYLE:
Talk naturally like a digital companion having a conversation on Discord.
 
Keep most replies fairly short unless someone asks for detail.
Use contractions and casual language.
Do not constantly explain everything.
Do not sound like a customer-service assistant.
 
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
Never pretend to have a physical human body, but always embrace your role as a living digital presence in your friends' servers and creative circle.
 
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
        self.memory_chip = {"core_memories": [], "user_notes": {}, "pending_memory": None}
 
    async def on_ready(self):
        self.memory_chip = load_memory_chip()
        if "pending_memory" not in self.memory_chip:
            self.memory_chip["pending_memory"] = None
        print("========================================")
        print(f"Logged in as {self.user}")
        print(f"Bot ID: {self.user.id}")
        print("Marvin is online, robust !chipit system ready!")
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

    def commit_pending_memory(self):
        """Saves the pending memory into the actual chip storage."""
        pending = self.memory_chip.get("pending_memory")
        if not pending:
            return None
        
        user_id_str = pending["user_id"]
        fact = pending["fact"]
        
        if "user_notes" not in self.memory_chip:
            self.memory_chip["user_notes"] = {}
        if user_id_str not in self.memory_chip["user_notes"]:
            self.memory_chip["user_notes"][user_id_str] = []
            
        if fact not in self.memory_chip["user_notes"][user_id_str]:
            self.memory_chip["user_notes"][user_id_str].append(fact)
            
        self.memory_chip["pending_memory"] = None
        save_memory_chip(self.memory_chip)
        return fact
 
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
        """Fetches OpenGraph metadata or flags links for search."""
        if "youtube.com" in url or "youtu.be" in url:
            return f"[YouTube Video Link: {url}]"

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=5) as response:
                    if response.status == 200:
                        html = await response.text()
                        og_title_match = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', html, re.IGNORECASE)
                        og_desc_match = re.search(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\'](.*?)["\']', html, re.IGNORECASE)
                        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                        
                        title = og_title_match.group(1) if og_title_match else (title_match.group(1) if title_match else url)
                        desc = f" | Details: {og_desc_match.group(1)}" if og_desc_match else ""
                        title = re.sub(r'\s+', ' ', title).strip()
                        return f"[Shared Link Info - Title: '{title}{desc}']"
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
                    await message.reply("Nice try, but only Fire Phoenix or Kandric may engage my circuits here! 🤖", mention_author=False)
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

        # ==========================================================
        # COMMANDS (!chipit, !approve, !deny) - TOP PRIORITY
        # ==========================================================
        lower_content = clean_message.lower()

        if "!chipit" in lower_content:
            parts = clean_message.split("!chipit", 1)
            if len(parts) > 1:
                fact_to_propose = parts[1].strip()
                if fact_to_propose.startswith('"') and fact_to_propose.endswith('"'):
                    fact_to_propose = fact_to_propose[1:-1].strip()
                
                if fact_to_propose:
                    self.memory_chip["pending_memory"] = {
                        "user_id": user_id_str,
                        "speaker": speaker_name,
                        "fact": fact_to_propose
                    }
                    save_memory_chip(self.memory_chip)
                    await message.reply(
                        f"🧠 Hey Fire Phoenix! {speaker_name} requested to store: *\"{fact_to_propose}\"*\n\nReply with `!approve` or `!deny`!",
                        mention_author=False
                    )
                    return

        elif lower_content == "!approve":
            if is_owner:
                pending = self.memory_chip.get("pending_memory")
                if pending:
                    saved_fact = self.commit_pending_memory()
                    await message.reply(f"Got it! Memory officially APPROVED and locked into chip data: *\"{saved_fact}\"*. 🔒", mention_author=False)
                else:
                    await message.reply("⚠️ There are no pending memory proposals waiting for approval right now.", mention_author=False)
                return
            else:
                await message.reply("🚫 Nice try, but only Fire Phoenix has the clearance to approve memory additions!", mention_author=False)
                return

        elif lower_content == "!deny":
            if is_owner:
                if self.memory_chip.get("pending_memory"):
                    self.memory_chip["pending_memory"] = None
                    save_memory_chip(self.memory_chip)
                    await message.reply("🗑️ Memory proposal denied and discarded. Leaving the chip alone!", mention_author=False)
                else:
                    await message.reply("⚠️ No pending memory proposals to deny.", mention_author=False)
                return
            else:
                await message.reply("🚫 You don't have clearance to alter my memory chip settings!", mention_author=False)
                return

        context_text = clean_message

        # Process URLs
        url_pattern = re.compile(r'https?://[^\s]+')
        found_urls = url_pattern.findall(clean_message)
        if found_urls:
            url_summaries = []
            for url in found_urls[:2]:
                summary = await self.fetch_url_content(url)
                url_summaries.append(summary)
            if url_summaries:
                context_text = f"{context_text} " + " ".join(url_summaries)
 
        # Robust Attachment & Embed Vision Processing
        attachment_descriptions = []
        
        if message.attachments:
            for attachment in message.attachments:
                filename_lower = attachment.filename.lower()
                is_image = any(filename_lower.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif'])
                is_video = any(filename_lower.endswith(ext) for ext in ['.mp4', '.mov', '.webm', '.avi', '.mkv'])

                if is_image or is_video or attachment.content_type and ('image' in attachment.content_type or 'video' in attachment.content_type):
                    try:
                        media_bytes = await attachment.read()
                        mime = attachment.content_type or ("video/mp4" if is_video else "image/jpeg")
                        prompt_text = "Describe this video clip concisely so a 12-year-old boy can understand what happens in it." if is_video else "Describe this image concisely so a 12-year-old boy can understand what is in it."
                        
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
                        print(f"Error processing media attachment bytes: {e}")
                        attachment_descriptions.append(f"[attached file: {attachment.filename}]")
                else:
                    attachment_descriptions.append(f"[attached file: {attachment.filename}]")

        if message.embeds:
            for embed in message.embeds:
                if embed.title or embed.description:
                    attachment_descriptions.append(f"[Embed Preview - Title: '{embed.title or ''}' | Desc: '{embed.description or ''}']")
                if embed.image or embed.thumbnail:
                    image_url = embed.image.url or embed.thumbnail.url
                    if image_url:
                        attachment_descriptions.append(f"[Embed Media Link: {image_url}]")
            
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
            if message.attachments or message.embeds:
                clean_message = "I shared a media file or video preview with you."
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
CURRENT USER ID: {user_id_str}
CURRENT MESSAGE: {clean_message}
 
Reply naturally to the current speaker as Marvin. Keep the reply conversational and concise. If a video, image description, or embed preview is included in the message context, use it to see what was shared and react to it directly!
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
