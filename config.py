# app/utils/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    SUPABASE_URL: str = os.getenv("REACT_APP_SUPABASE_URL")
    SUPABASE_ANON_KEY: str = os.getenv("REACT_APP_SUPABASE_ANON_KEY")



settings = Settings()

