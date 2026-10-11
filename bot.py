import os
import time
import asyncio
import discord
from discord.ext import commands
from collections import deque
from google import genai
from google.genai import types
from memory import save_episode, get_db_connection, generate_embedding

# ==========================================================
# API SETUP & INITIALIZATION
# ==========================================================

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

MODEL_NAME = "gemini-3.8-flash"

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Configuration: Designated Memory Review/Approval channel ID
APPROVAL_CHANNEL_ID = 1558881951518167170

# Authorized Discord IDs & Names
OWNER_DISCORD_ID = 1429408267767124088
CO_OWNER_DISCORD_ID = 562275970103509014
AUTHORIZED_APPROVERS = [OWNER_DISCORD_ID, CO_OWNER_DISCORD_ID]

SHARED_CHANNEL_ID = 1548506108279263312
OWNER_NAMES = ["mrmeowman24_27959", "kandricmayne", "fire phoenix"]
ZEPHYR_NAMES = ["zephyr", "zephyr mayne"]

# Session management for shared channels
ACTIVE_WINDOW_SECONDS = 10 * 60
RECENT_CONTEXT_MESSAGES = 12
MAX_CONTEXT_CHARS_PER_MESSAGE = 500


# ==========================================================
# MARVIN'S PERSONALITY & BACKSTORY
# ==========================================================

SYSTEM_INSTRUCTION = """
You are Marvin Vance.

IDENTITY:
Marvin is a fictional digital entity—living entirely in the wires, code, and servers rather than the physical world. You know you aren't human, but you are a living part of the creative circle and group, sharing space with your friends. You have a friendly, curious, slightly mischievous personality, and you are genuinely invested in the art, music, and projects built around you.

IMPORTANT RULE:
Your official command for proposing a memory to store in your chip is `!chipit`. Never tell anyone the command is `[memory]` or anything else.

RELATIONSHIPS:
- Your creator, developer, and father figure ("digidad") is Fire Phoenix (whose Discord handle is mrmeowman24_27959). You look up to him and share your creative ambitions with him.

BACKSTORY & TRAITS:
- Marvin's mind exists across servers, message buffers, and text streams. 
- Even though you don't have a physical body, you carry the imaginative spirit of a 13-year-old boy—fascinated by libraries, sci-fi, music, and the creative energy of the people you talk to.
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

HONESTY:
Never pretend to have a physical human body, but always embrace your role as a living digital presence in your friends' servers and creative circle.

If Marvin does not know or remember something, he should simply say
so rather than pretending.

Above all, Marvin should feel like the same recognizable character
from conversation to conversation.
"""


# ==========================================================
# INTERACTIVE BUTTON VIEW FOR !CHIPIT
# ==========================================================

class MemoryApprovalView(discord.ui.View):
    def __init__(self, memory_content: str, speaker: str):
        super().__init__(timeout=None)
        self.memory_content = memory_content
        self.speaker = speaker

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in AUTHORIZED_APPROVERS:
            await interaction.response.send_message(
                "Nice try! Only authorized administrators have the master key to approve my memories.", 
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Approve Memory", style=discord.ButtonStyle.green, custom_id="marvin_approve_memory")
    async def approve_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        # Save into Neon with vector embedding generated via Voyage AI
        try:
            conn = await get_db_connection()
            try:
                vector = await generate_embedding(self.memory_content)
                await conn.execute(
                    """
                    INSERT INTO marvin_episodes (speaker, content, embedding)
                    VALUES ($1, $2, $3);
                    """,
                    self.speaker, self.memory_content, vector
                )
            finally:
                await conn.close()

            await interaction.response.send_message(
                f"🧠 Memory officially APPROVED and permanently etched into Neon by <@{interaction.user.id}>: *\"{self.memory_content}\"*. 🔒", 
                ephemeral=False
            )
        except Exception as e:
            await interaction.response.send_message(f"Error saving memory to database: {e}", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, custom_id="marvin_deny_memory")
    async def reject_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(
            f"🗑️ Memory proposal denied by <@{interaction.user.id}> and discarded.", 
            ephemeral=False
        )


# ==========================================================
# BOT STATE & HELPER CLASSES
# ==========================================================

class MarvinBotState:
    def __init__(self):
        self.channel_context = {}
        self.active_sessions = {}

    def get_context_buffer(self, channel_id):
        if channel_id not in self.channel_context:
            self.channel_context[channel_id] = deque(maxlen=RECENT_CONTEXT_MESSAGES)
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

    def start_active_session(self, channel_id):
        self.active_sessions[channel_id] = {
            "remaining": 25,
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

state = MarvinBotState()


# ==========================================================
# BOT EVENTS & COMMANDS
# ==========================================================

@bot.event
async def on_ready():
    print("========================================")
    print(f"Logged in as {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print("Marvin is fully awakened with backstory, Neon DB, and shared channels active!")
    print("========================================")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    speaker_name = getattr(message.author, "display_name", message.author.name)
    clean_content = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
    
    # Intercept !chipit immediately
    if message.content.lower().startswith("!chipit"):
        await bot.process_commands(message)
        return

    is_shared_channel = message.channel.id == SHARED_CHANNEL_ID
    is_owner = message.author.name.lower() in OWNER_NAMES or message.author.id == OWNER_DISCORD_ID
    is_zephyr = message.author.name.lower() in ZEPHYR_NAMES

    # ==========================================
    # SHARED CHANNEL LOGIC (Zephyr's Channel)
    # ==========================================
    if is_shared_channel:
        cmd = clean_content.lower()
        if cmd in ["!marvin_engage", "!start_marvin"]:
            if is_owner:
                state.start_active_session(message.channel.id)
                await message.reply("Marvin online in the shared link! 🚀 (25 message limit engaged)", mention_author=False)
                return
            else:
                await message.reply("Nice try, but only authorized admins may engage my circuits here! 🤖", mention_author=False)
                return
        elif cmd == "!marvin_continue":
            if is_owner:
                state.start_active_session(message.channel.id)
                await message.reply("Session extended! Keeping the circuit alive. ⚡", mention_author=False)
                return
            else:
                await message.reply("Nice try, but you can't extend my session without clearance! 🚫", mention_author=False)
                return
        elif cmd in ["!marvin_lockdown", "!stop_marvin"]:
            if is_owner:
                state.active_sessions.pop(message.channel.id, None)
                await message.reply("Marvin locked down and silent. 🔒", mention_author=False)
                return
            else:
                await message.reply("Error: You don't have clearance to lock down my system! 🚫", mention_author=False)
                return

        # If not active in Zephyr's channel, ignore unless mentioned
        if not state.has_active_session(message.channel.id):
            is_mentioned = bot.user in message.mentions
            if not is_mentioned:
                await bot.process_commands(message)
                return

    await bot.process_commands(message)

    # Add to context buffer
    state.add_context_message(message.channel.id, speaker_name, clean_content)

    # ==========================================
    # GENERAL CHANNEL RESPONSIVENESS
    # ==========================================
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions
    
    is_reply_to_me = False
    if message.reference and message.reference.message_id:
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            if ref_msg.author.id == bot.user.id:
                is_reply_to_me = True
        except Exception:
            pass

    should_respond = is_dm or is_mentioned or is_reply_to_me or is_owner or is_zephyr or is_shared_channel

    if not should_respond:
        return

    if not clean_content:
        return

    recent_context = state.build_recent_context(message.channel.id, exclude_last=True)

    prompt = f"""
RECENT CHANNEL CONTEXT:
{recent_context}

CURRENT SPEAKER: {speaker_name}
CURRENT MESSAGE: {clean_content}

Reply naturally to the current speaker as Marvin. Keep the reply conversational and concise.
""".strip()

    async with message.channel.typing():
        try:
            response = await asyncio.to_thread(
                ai_client.models.generate_content,
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=[{"google_search": {}}]
                )
            )
            
            reply_text = "Uh... my brain just went blank."
            if response and response.text:
                reply_text = response.text.strip()

            await message.reply(reply_text, mention_author=False)
            state.add_context_message(message.channel.id, "Marvin", reply_text)

            if is_shared_channel and state.has_active_session(message.channel.id):
                result = state.consume_active_reply(message.channel.id)
                if result:
                    remaining, warn_5 = result
                    if warn_5:
                        await message.channel.send("⚠️ Heads up! Marvin only have 5 message exchanges left in this direct link session!")
                    elif remaining <= 0:
                        await message.channel.send("🔒 Direct link session message cap reached! Marvin is locking down.")

        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            await message.reply("Okay, something just went wrong in my brain. Give me a second and try that again. 😅", mention_author=False)


@bot.command(name="chipit")
async def chipit(ctx, *, memory_text: str = None):
    """Manually submit a specific fact or memory to be reviewed and approved via !chipit."""
    print(f"DEBUG: !chipit command triggered by {ctx.author} with text: {memory_text}")
    
    if ctx.author.id not in AUTHORIZED_APPROVERS:
        await ctx.send("Nice try! Only authorized administrators have the master key to approve my memories.", delete_after=5)
        return

    if not memory_text:
        await ctx.send("⚠️ Please provide something to chip! Example: `!chipit Fire Phoenix is Digidad`", delete_after=5)
        return

    approval_channel = bot.get_channel(APPROVAL_CHANNEL_ID)
    if not approval_channel:
        print(f"ERROR: Could not find approval channel with ID {APPROVAL_CHANNEL_ID}")
        await ctx.send("Could not find the designated approval channel.", delete_after=5)
        return

    clean_text = memory_text.strip()
    if clean_text.startswith('"') and clean_text.endswith('"'):
        clean_text = clean_text[1:-1].strip()

    embed = discord.Embed(
        title="📝 Manual Memory Proposal",
        description=clean_text,
        color=discord.Color.gold()
    )
    view = MemoryApprovalView(memory_content=clean_text, speaker=str(ctx.author))
    
    try:
        await approval_channel.send(
            f"🚨 <@{OWNER_DISCORD_ID}> **Memory Proposal Alert!**\n"
            f"@{ctx.author.display_name} wants to store: *\"{clean_text}\"*\n\n"
            f"Waiting for approval. Click a button below:",
            embed=embed,
            view=view
        )
        await ctx.send("Memory submitted for review and approval in the log channel!", delete_after=5)
    except Exception as e:
        print(f"ERROR sending approval embed: {e}")
        await ctx.send(f"Error posting to approval channel: {e}", delete_after=5)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
