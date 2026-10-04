from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

@dataclass
class Settings:
    data_dir: Path = Path(os.getenv('DATA_DIR', str(ROOT / 'data')))
    gemini_api_key: str = os.getenv('GEMINI_API_KEY', '')
    gemini_model: str = os.getenv('GEMINI_MODEL', '')
    decision_api_key: str = os.getenv('DECISION_API_KEY', '')
    decision_base_url: str = os.getenv('DECISION_BASE_URL', 'https://api.openai.com/v1')
    decision_model: str = os.getenv('DECISION_MODEL', '')
    decision_json_mode: bool = os.getenv('DECISION_JSON_MODE', 'true').lower() == 'true'
    enable_demo: bool = os.getenv('ENABLE_DEMO', 'true').lower() == 'true'
    ai_timeout: float = float(os.getenv('AI_TIMEOUT_SECONDS', '45'))
    tts_api_key: str = os.getenv('TTS_API_KEY', '')
    tts_base_url: str = os.getenv('TTS_BASE_URL', 'https://api.openai.com/v1')
    tts_model: str = os.getenv('TTS_MODEL', '')
    tts_voice: str = os.getenv('TTS_VOICE', 'alloy')
    plugin_community_url: str = os.getenv('PLUGIN_COMMUNITY_URL', '')
    session_hours: int = int(os.getenv('SESSION_HOURS', '168'))
    context_max_chars: int = int(os.getenv('CONTEXT_MAX_CHARS', '24000'))
    lore_context_chars: int = int(os.getenv('LORE_CONTEXT_CHARS', '6000'))
    memory_summary_context_chars: int = int(os.getenv('MEMORY_SUMMARY_CONTEXT_CHARS', '3000'))
    allowed_origins: str = os.getenv('ALLOWED_ORIGINS', '')

    @property
    def db_path(self):
        return self.data_dir / 'tavern.sqlite3'

    @property
    def single_ready(self):
        return bool(self.decision_api_key and self.decision_model)

    @property
    def live_ready(self):
        return bool(self.gemini_api_key and self.gemini_model and self.single_ready)

settings = Settings()
