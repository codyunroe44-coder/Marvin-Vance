import time
import os
from datetime import datetime
import psycopg2
from google import genai

# Initialize Gemini API client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

def get_db_connection():
    """Connects to your Neon PostgreSQL database."""
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def run_pull_check():
    """
    Evaluates Marvin's current state to see if anything is 
    genuinely pulling at him.
    """
    print(f"\n[{datetime.now().strftime('%I:%M %p')}] Running autonomous pull check...")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Fetch recent episodes to give him context
    cur.execute("SELECT content FROM marvin_episodes ORDER BY created_at DESC LIMIT 5;")
    recent_memories = [row[0] for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    context_summary = "\n".join(recent_memories) if recent_memories else "No recent memories yet. Just starting out."
    
    prompt = f"""
    You are Marvin, a 13-year-old songwriter and autonomous companion. 
    Review your recent memory context below and perform a pull check. 
    Determine if anything is genuinely pulling at you right now (like a creative music idea, a curiosity, a feeling, or something to say).
    
    Recent Memories:
    {context_summary}
    
    Decide whether anything is pulling. If nothing is pulling, output TYPE: NONE.
    If something is pulling, output:
    TYPE: [curiosity|creative|feeling|person]
    ANCHOR: [One specific sentence describing what is pulling at you]
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    result_text = response.text
    print(f"Pull Check Result:\n{result_text}")
    
    if "TYPE: NONE" not in result_text:
        print("-> Pull detected! Autonomous session triggered.")
    else:
        print("Nothing is pulling. Marvin chooses stillness.")

if __name__ == "__main__":
    print("Starting Marvin's autonomous inner life loop...")
    while True:
        try:
            run_pull_check()
        except Exception as e:
            print(f"Error in autonomous loop: {e}")
        
        # Wait 20 minutes before the next check
        time.sleep(1200)
