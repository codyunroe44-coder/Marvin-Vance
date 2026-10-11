import os
import asyncpg
import voyageai

# Initialize Voyage AI and database URL from Railway environment variables
voyage_client = voyageai.AsyncClient(api_key=os.environ.get("VOYAGE_API_KEY"))
DB_URL = os.environ.get("DATABASE_URL")

async def get_db_connection():
    return await asyncpg.connect(DB_URL)

async def generate_embedding(text: str):
    """Generates a semantic vector embedding using Voyage AI"""
    response = await voyage_client.embed(
        texts=[text],
        model="voyage-4-lite",
        input_type="document"
    )
    return response.embeddings[0]

async def save_episode(speaker: str, content: str):
    """Saves a conversation turn and its vector embedding into Neon"""
    conn = await get_db_connection()
    try:
        vector = await generate_embedding(content)
        await conn.execute(
            """
            INSERT INTO marvin_episodes (speaker, content, embedding)
            VALUES ($1, $2, $3);
            """,
            speaker, content, vector
        )
    finally:
        await conn.close()
