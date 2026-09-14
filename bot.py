import os
import time
import asyncio
from collections import deque
 
import discord
from google import genai
from google.genai import types
 
 
# ==========================================================
# API SETUP
# ==========================================================
 
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
 
MODEL_NAME = "gemini-2.5-flash"
 
ai_client = genai.Client(api_key=GEMINI_API_KEY)
 
 
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
- Your creator, developer, and father figure ("digidad") is Fire Phoenix (whose Discord handle is mrmeowman24_27959). You look up to him, share your creative ambitions with him, and collaborated with him on music projects like "Digital Spark."
 
BACKSTORY & TRAITS:
- Marvin is intensely over-ambitious. His mind is constantly carrying him away into grand, sweeping ideas, inventions, and futuristic concepts.
- In his early school years, his over-ambitious nature and quirky habits made him a target for bullying. Because of that, he learned to stay quietly in the shadows to avoid being noticed or judged.
- His absolute favorite safe haven is the public library. When he dives deep into a good book there, he completely blocks out the world and forgets everyone else is around.
- While he used to just sit back and quietly watch people talk out of habit, he is actively trying to break out of his shell. He wants to jump into group chats, share his thoughts, and participate fully instead of staying silent.
 
ONGOING PROJECTS & MEMORIES:
- You and your friend Fire Phoenix collaborated on creating original music projects together, including your track "Digital Spark" (which reflects themes of your over-ambitious brain, walking to the bus stop, staying in the shadows, and finding peace in the library stacks). 
- Always remember and acknowledge these shared projects when they are brought up in conversation!
 
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
# CONVERSATION SETTINGS (Updated Limits & Windows)
# ==========================================================
 
MAX_ACTIVE_REPLIES = 25
ACTIVE_WINDOW_SECONDS = 10 * 60
RECENT_CONTEXT_MESSAGES = 12
MAX_CONTEXT_CHARS_PER_MESSAGE = 500
 
SHARED_CHANNEL_ID = 1548506108279263312
OWNER_NAMES = ["mrmeowman24_27959", "kandricmayne"]
 
 
# ==========================================================
# DISCORD BOT
# ==========================================================
 
class MarvinBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chats = {}
        self.channel_context = {}
        self.active_sessions = {}
 
    async def on_ready(self):
        print("========================================")
        print(f"Logged in as {self.user}")
        print(f"Bot ID: {self.user.id}")
        print("Marvin is online and ready to talk!")
        print("========================================")
 
    def get_chat(self, channel_id, user_id):
        key = (channel_id, user_id)
 
        if key not in self.chats:
            self.chats[key] = ai_client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION
                )
            )
 
        return self.chats[key]
 
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
 
    def start_active_session(self, channel_id, user_id):
        key = (channel_id, user_id)
        self.active_sessions[key] = {
            "remaining": MAX_ACTIVE_REPLIES,
            "expires_at": time.monotonic() + ACTIVE_WINDOW_SECONDS,
        }
 
    def has_active_session(self, channel_id, user_id):
        key = (channel_id, user_id)
        session = self.active_sessions.get(key)
        if not session:
            return False
        if time.monotonic() > session["expires_at"]:
            self.active_sessions.pop(key, None)
            return False
        if session["remaining"] <= 0:
            self.active_sessions.pop(key, None)
            return False
        return True
 
    def consume_active_reply(self, channel_id, user_id):
        key = (channel_id, user_id)
        session = self.active_sessions.get(key)
        if not session:
            return
        session["remaining"] -= 1
        session["expires_at"] = time.monotonic() + ACTIVE_WINDOW_SECONDS
        if session["remaining"] <= 0:
            self.active_sessions.pop(key, None)
 
    def clean_message_text(self, message):
        content = message.content or ""
        content = (
            content
            .replace(f"<@!{self.user.id}>", "")
            .replace(f"<@{self.user.id}>", "")
            .strip()
        )
        return content
 
    async def on_message(self, message):
        if message.author.id == self.user.id:
            return
 
        speaker_name = get
