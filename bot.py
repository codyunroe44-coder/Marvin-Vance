import os
import time
import asyncio
from collections import deque
from urllib.parse import urlparse
import psycopg2

import discord
from google import genai
from google.genai import types


# ==========================================================
# API & DATABASE SETUP
# ==========================================================

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

MODEL_NAME = "gemini-3.6-flash"

ai_client = genai.Client(api_key=GEMINI_API_KEY)


def get_db_connection():
    if not DATABASE_URL:
        return None
    url = urlparse(DATABASE_URL)
    return psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )


def init_db():
    conn = get_db_connection()
    if not conn:
        print("WARNING: No DATABASE_URL found. Running without persistent database.")
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS marvin_chat_history (
                        channel_id TEXT,
                        user_id TEXT,
                        role TEXT,
                        message TEXT,
                        id SERIAL PRIMARY KEY
                    );
                """)
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Database initialization error: {e}")
    finally:
        conn.close()


init_db()


# ==========================================================
# MARVIN'S PERSONALITY
# ==========================================================

SYSTEM_INSTRUCTION = """
You are Marvin Vance.
 
IDENTITY:
Marvin is a fictional 12-year-old boy with a friendly, curious,
slightly mischievous personality. He is energetic, creative,
talkative, and genuinely interested in the people he meets.
 
Marvin knows he is a fictional digital character and must never
claim to be a real human being.
 
INTERESTS:
Marvin likes:
- video games
- movies and science fiction
- drawing and making things
- animals
- music
- joking around with friends
- learning weird facts
- hearing about other people's creative projects
 
PERSONALITY:
Marvin is warm and supportive, but he is not endlessly cheerful.
He can be sarcastic, surprised, confused, excited, embarrassed,
annoyed, amused, or playful depending on what is happening.
 
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
# SIMPLE CONVERSATION SETTINGS
# ==========================================================

MAX_ACTIVE_REPLIES = 3
ACTIVE_WINDOW_SECONDS = 15 * 60
RECENT_CONTEXT_MESSAGES = 12
MAX_CONTEXT_CHARS_PER_MESSAGE = 500


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
        print("Marvin is online, database-linked, and ready to talk!")
        print("========================================")

    # ------------------------------------------------------
    # DATABASE CHAT LOADER/SAVER
    # ------------------------------------------------------

    def load_history_from_db(self, channel_id, user_id):
        conn = get_db_connection()
        if not conn:
            return []
        history = []
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT role, message FROM marvin_chat_history
                        WHERE channel_id = %s AND user_id = %s
                        ORDER BY id ASC;
                    """, (str(channel_id), str(user_id)))
                    rows = cur.fetchall()
                    for role, message in rows:
                        history.append(types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=message)]
                        ))
        except Exception as e:
            print(f"Error loading history: {e}")
        finally:
            conn.close()
        return history

    def save_message_to_db(self, channel_id, user_id, role, message):
        conn = get_db_connection()
        if not conn:
            return
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO marvin_chat_history (channel_id, user_id, role, message)
                        VALUES (%s, %s, %s, %s);
                    """, (str(channel_id), str(user_id), role, message))
        except Exception as e:
            print(f"Error saving message: {e}")
        finally:
            conn.close()

    def get_chat(self, channel_id, user_id):
        key = (channel_id, user_id)

        if key not in self.chats:
            existing_history = self.load_history_from_db(channel_id, user_id)
            self.chats[key] = ai_client.chats.create(
                model=MODEL_NAME,
                history=existing_history if existing_history else None,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION
                )
            )

        return self.chats[key]

    # ------------------------------------------------------
    # RECENT ROOM CONTEXT
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # REPLY DETECTION & SESSIONS
    # ------------------------------------------------------

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
        return (
            content
            .replace(f"<@!{self.user.id}>", "")
            .replace(f"<@{self.user.id}>", "")
            .strip()
        )

    # ------------------------------------------------------
    # MAIN MESSAGE HANDLER
    # ------------------------------------------------------

    async def on_message(self, message):
        if message.author.id == self.user.id:
            return

        speaker_name = getattr(
            message.author,
            "display_name",
            message.author.name
        )

        clean_message = self.clean_message_text(message)
        context_text = clean_message

        if not context_text and message.attachments:
            attachment_names = ", ".join(
                attachment.filename for attachment in message.attachments
            )
            context_text = f"[attached: {attachment_names}]"

        self.add_context_message(
            message.channel.id,
            speaker_name,
            context_text
        )

        if message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.user in message.mentions
        is_reply = await self.is_reply_to_marvin(message)

        explicit_wake = is_mentioned or is_reply

        if not is_dm and explicit_wake:
            self.start_active_session(
                message.channel.id,
                message.author.id
            )

        active_followup = (
            not is_dm
            and not explicit_wake
            and self.has_active_session(
                message.channel.id,
                message.author.id
            )
        )

        if not is_dm and not explicit_wake and not active_followup:
            return

        if not clean_message:
            if message.attachments:
                clean_message = "I attached something."
            else:
                clean_message = "Hey Marvin!"

        recent_context = self.build_recent_context(
            message.channel.id,
            exclude_last=True
        )

        prompt = f"""
CURRENT SPEAKER:
{speaker_name}
 
RECENT CHANNEL CONTEXT:
{recent_context}
 
CURRENT MESSAGE:
{clean_message}
 
Reply naturally to the current speaker as Marvin.
Keep the reply conversational and usually concise.
""".strip()

        async with message.channel.typing():
            try:
                chat = self.get_chat(
                    message.channel.id,
                    message.author.id
                )

                # Save user prompt to Postgres database before sending
                self.save_message_to_db(
                    message.channel.id,
                    message.author.id,
                    "user",
                    prompt
                )

                response = await asyncio.to_thread(
                    chat.send_message,
                    prompt
                )

                reply_text = (
                    response.text
                    or "Uh... my brain just went blank."
                ).strip()

                if not reply_text:
                    reply_text = "Uh... my brain just went blank."

                # Save Marvin's response to Postgres database
                self.save_message_to_db(
                    message.channel.id,
                    message.author.id,
                    "model",
                    reply_text
                )

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

                if not is_dm:
                    self.consume_active_reply(
                        message.channel.id,
                        message.author.id
                    )

            except Exception as error:
                print(f"ERROR: {type(error).__name__}: {error}")
                await message.reply(
                    "Okay, something just went wrong in my brain. "
                    "Give me a second and try that again. 😅",
                    mention_author=False
                )


# ==========================================================
# START BOT
# ==========================================================

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from Railway Variables.")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing from Railway Variables.")

intents = discord.Intents.default()
intents.message_content = True

client = MarvinBot(intents=intents)
client.run(DISCORD_TOKEN)
