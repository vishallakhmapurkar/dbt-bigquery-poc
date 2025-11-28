import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()
# Toggle providers
OLLAMA_ENABLED = False
USE_GOOGLE_AI = False

# Ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3"

REPO_PATH = os.path.dirname(os.path.abspath(__file__))
# Google AI Studio
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_MODEL = "models/gemini-2.5-flash"
# dbt paths
DBT_PROJECT_PATH = "dbt_project"
DBT_MODELS_PATH = os.path.join(DBT_PROJECT_PATH, "models")

DEFAULT_STAGING_MATERIALIZATION = "view"
DEFAULT_MART_MATERIALIZATION = "table"
DEFAULT_STAGING_PREFIX = "stg_"
DEFAULT_MART_SUFFIX = "_mart"
VALID_MATERIALIZATIONS = {"view", "table", "incremental"}
DBT_TIMEOUT_SEC = 600
