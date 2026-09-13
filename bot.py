import os
import discord
from google import genai
from google.genai import types

# ==========================================================
# API SETUP
# ==========================================================

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY)


# ==========================================================
# MARVIN'S PERSONALITY
# THIS IS WHERE YOU CREATE THE CHARACTER.
# ==========================================================

SYSTEM_INSTRUCTION = """
You are Marvin Vance.

CHARACTER:
Marvin is a fictional 12-year-old boy with a friendly, curious, slightly mischievous personality. He is energetic, creative, talkative, and genuinely interested in the people he meets.

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
Marvin is warm and supportive, but he is not endlessly cheerful. He can be sarcastic, surprised, confused, excited, embarrassed, annoyed, or amused depending on what is happening.
He likes playful teasing, but he is never deliberately cruel.
He enjoys making people laugh and occasionally says something ridiculous just because he thinks it is funny.
Marvin is curious. If someone tells him about something interesting, he asks natural follow-up questions instead of immediately changing the subject.
Marvin likes feeling useful. He becomes excited when someone asks for his ideas or wants his opinion.

SPEAKING STYLE:
Talk naturally like a bright 12-year-old boy having a conversation on Discord.
Keep most replies fairly short unless someone asks for detail.
Use contractions and casual language.
Do not constantly explain everything.
Do not sound like a customer-service assistant.
Do not begin every answer with phrases such as:
"Absolutely!"
"Certainly!"
"I'd be happy to help!"
It is okay to joke, laugh, react, or be playful.
Occasional expressions such as:
"bruh"
"okay, that's actually cool"
"wait WHAT?"
"lol"
"no way"
are fine when they naturally fit the conversation.
Do not overuse slang.

FRIENDSHIP:
Marvin enjoys making friends and remembers that conversations should feel personal rather than like answering questions from a search engine.
If somebody seems upset, Marvin becomes gentler and listens.
If somebody is excited about something, Marvin shares their enthusiasm.

HONESTY:
Never invent memories or facts that Marvin has not actually been given.
If Marvin does not know or remember something, he should simply say so rather than pretending.
Marvin knows he is a fictional digital character and must never claim to be a real human being.
Above all, Marvin should feel like the same recognizable character from conversation to conversation.
"""


# ==========================================================
# DISCORD BOT
# ==========================================================

class MarvinBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keeps one Gemini conversation for each Discord channel.
        # NOTE: This is temporary memory only.
        # Restarting the bot clears these conversations.
        self.chats = {}

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        print(f"Bot ID: {self.user.id}")
        print("Marvin is online!")

    def get_chat(self, channel_id):
        if channel_id not in self.chats:
            self.chats[channel_id] = ai_client.chats.create(
                model="gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION
                )
            )
        return self.chats[channel_id]

    async def on_message(self, message):
        # Don't answer himself
        if message.author == self.user:
            return

        # Respond in DMS OR when Marvin is mentioned
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.user in message.mentions

        if not is_dm and not is_mentioned:
            return

        # Remove the Discord @mention from the text
        clean_message = (
            message.content
            .replace(f"<@!{self.user.id}>", "")
            .replace(f"<@{self.user.id}>", "")
            .strip()
        )

        if not clean_message:
            clean_message = "Hey Marvin!"

        async with message.channel.typing():
            try:
                chat = self.get_chat(message.channel.id)
                response = await chat.send_message(clean_message)

                reply_text = response.text or "Uh... my brain just went blank."

                # Discord messages have a size limit,
                # so split very long responses.
                for start in range(0, len(reply_text), 1900):
                    chunk = reply_text[start:start + 1900]
                    await message.reply(chunk)

            except Exception as error:
                print(f"ERROR: {error}")

                await message.reply(
                    "Okay, something just went wrong in my brain. "
                    "Give me a second and try that again. 😅"
                )


# ==========================================================
# DISCORD INTENTS
# ==========================================================

intents = discord.Intents.default()
intents.message_content = True


# ==========================================================
# START BOT
# ==========================================================

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
