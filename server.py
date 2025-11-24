import os
import logging
import subprocess
import requests
import json
from typing import List, Optional, Dict, Any

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from settings import DBT_MODELS_PATH, DBT_PROJECT_PATH
import settings
import shutil
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="dbt Generator Service (deterministic + AI optional)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Models ----------------

class ColumnSpec(BaseModel):
    name: str
    type: Optional[str] = None
    description: Optional[str] = None

class TableSpec(BaseModel):
    name: str
    description: Optional[str] = None
    columns: List[ColumnSpec]
    incremental_timestamp: Optional[str] = None

class JsonSpec(BaseModel):
    source_name: str
    database: Optional[str] = None
    schema_name: Optional[str] = Field(default=None, alias="schema")
    tables: List[TableSpec]
    generate_marts: bool = True
    generate_model_schema_yml: bool = True

    class Config:
        populate_by_name = True

class GenerationOptions(BaseModel):
    staging_materialization: str = settings.DEFAULT_STAGING_MATERIALIZATION
    mart_materialization: str = settings.DEFAULT_MART_MATERIALIZATION
    naming_convention_staging_prefix: str = settings.DEFAULT_STAGING_PREFIX
    naming_convention_mart_suffix: str = settings.DEFAULT_MART_SUFFIX
    include_docs: bool = True
    include_tests: bool = False

class InteractivePayload(BaseModel):
    spec: JsonSpec
    options: GenerationOptions

# ---------------- Prompt Builder ----------------

def build_dbt_prompt(spec: JsonSpec, table: TableSpec, options: GenerationOptions) -> str:
    column_list = ", ".join([c.name for c in table.columns])
    desc = table.description or "No description provided"

    return f"""You are a SQL generator for dbt models targeting BigQuery.

Source: {spec.source_name}
Database: {spec.database or 'default_db'}
Schema: {spec.schema_name or 'default_schema'}
Table: {table.name}
Description: {desc}
Columns: {column_list}

Requirements:
- Use BigQuery standard SQL.
- At the top include {{ config(materialized='{options.staging_materialization}') }}.
- Select from {{ source('{spec.source_name}', '{table.name}') }}.
- Rename id → {table.name}_id, user_id → customer_id.
- Keep other columns as is.
- Output only SQL code, no commentary.
"""

# ---------------- AI Clients ----------------

def call_ollama(prompt: str, model: str = settings.OLLAMA_MODEL,
                stream: bool = False, timeout: int = 30) -> str:
    if not settings.OLLAMA_ENABLED:
        return ""
    try:
        payload = {"model": model, "prompt": prompt, "stream": stream}
        resp = requests.post(settings.OLLAMA_URL, json=payload, timeout=timeout, stream=stream)
        if stream:
            chunks = []
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode("utf-8"))
                    if "response" in obj:
                        chunks.append(obj["response"])
                except json.JSONDecodeError:
                    continue
            return "".join(chunks).strip() or ""
        else:
            data = resp.json()
            return data.get("response", "").strip() or ""
    except Exception as e:
        logging.warning(f"Ollama error: {e}")
        return ""
def clean_ai_sql(sql_text: str) -> str:
    # Remove markdown fences like ```sql ... ```
    return sql_text.replace("```sql", "").replace("```", "").strip()

def call_google_ai_studio(prompt: str, model: str = "models/gemini-2.5-flash") -> str:
    """
    Call Google AI Studio (Gemini 2.5 Flash).
    """
    if not getattr(settings, "GOOGLE_API_KEY", None):
        return ""
    url = f"https://generativelanguage.googleapis.com/v1/{model}:generateContent?key={settings.GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        resp = requests.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"]
        else:
            logging.warning(f"Google AI Studio error: {resp.text}")
        return ""
    except Exception as e:
        logging.warning(f"Google AI Studio call failed: {e}")
        return ""
def mart_sql(table: TableSpec, options: GenerationOptions) -> str:
    return (
            materialization_block(options.mart_materialization)
            + f"select * from {{{{ ref('{options.naming_convention_staging_prefix}{table.name}') }}}}"
    )
def write_source_schema(spec: JsonSpec):
    path = os.path.join(settings.DBT_PROJECT_PATH, "models", "schema.yml")
    source_def = {
        "version": 2,
        "sources": [
            {
                "name": spec.source_name,
                "database": spec.database,
                "schema": spec.schema_name,
                "tables": [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "columns": [
                            {"name": c.name, "description": c.description or ""}
                            for c in t.columns
                        ],
                    }
                    for t in spec.tables
                ],
            }
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(source_def, f, sort_keys=False)
    return path
# ---------------- Fallback Validator ----------------

def validate_sql(sql_text: str) -> bool:
    if not sql_text.strip():
        return False
    if "``" in sql_text:  # stray backticks
        return False
    if "{{ source(" not in sql_text and "{{ ref(" not in sql_text:
        return False
    if "{{ config(" not in sql_text:
        return False
    return True

# ---------------- Helpers ----------------

def generate_dbt_files(spec_json):
    """
    Generate dbt models (staging + marts) and schema.yml
    based on the provided JSON spec and options.
    Returns previews of all generated files.
    """
    try:
        # If input is a JSON string, parse it
        if isinstance(spec_json, str):
            import json
            spec_json = json.loads(spec_json)

        # If it's a custom object, normalize
        elif hasattr(spec_json, "dict"):
            spec_json = spec_json.dict()
        elif hasattr(spec_json, "__dict__"):
            spec_json = dict(spec_json.__dict__)

        # Now spec_json is guaranteed to be a dict
        spec = spec_json.get("spec", spec_json)
        options = spec_json.get("options", spec_json)


        print("DEBUG Options:", options)

        source_name = spec["source_name"]

        # --- Ensure base directories exist ---
        ensure_dirs()

        # --- Initialize schema.yml structure ---
        schema_dict = {"version": 2, "sources": [], "models": []}
        source_block = {"name": source_name, "schema": spec.get("schema", source_name), "tables": []}

        # Collect previews
        previews = {}

        # --- Process each table ---
        for table in spec.get("tables", []):
            table_name = table["name"]
            columns = table["columns"]

            # Build SELECT statement for staging
            select_columns = ",\n    ".join([f"{col['name']} AS {col['name']}" for col in columns])

            # --- Staging model SQL ---
            staging_model_name = f"{options.get('naming_convention_staging_prefix', 'stg_')}{table_name}"
            staging_sql = f"""
{{{{ config(materialized='{options.get('staging_materialization', 'view')}') }}}}

SELECT
    {select_columns}
FROM {{{{ source('{source_name}', '{table_name}') }}}}
"""
            staging_file = os.path.join(settings.DBT_MODELS_PATH, "staging", f"{staging_model_name}.sql")
            with open(staging_file, "w") as f:
                f.write(staging_sql.strip())
            previews[staging_file] = staging_sql.strip()

            # --- Mart model SQL (if enabled) ---
            if spec.get("generate_marts", False):
                mart_model_name = f"{table_name}{options.get('naming_convention_mart_suffix', '_mart')}"
                marts_sql = f"""
{{{{ config(materialized='{options.get('mart_materialization', 'table')}') }}}}

SELECT
    *
FROM {{{{ ref('{staging_model_name}') }}}}
"""
                marts_file = os.path.join(settings.DBT_MODELS_PATH, "marts", f"{mart_model_name}.sql")
                with open(marts_file, "w") as f:
                    f.write(marts_sql.strip())
                previews[marts_file] = marts_sql.strip()

            # --- Update schema.yml ---
            table_entry = {"name": table_name}
            if options.get("include_docs", False):
                table_entry["description"] = table.get("description", "")
            source_block["tables"].append(table_entry)

            schema_dict["models"].append({
                "name": staging_model_name,
                "description": f"Staging model for {table_name}" if options.get("include_docs", False) else ""
            })
            if spec.get("generate_marts", False):
                schema_dict["models"].append({
                    "name": mart_model_name,
                    "description": f"Mart model for {table_name}" if options.get("include_docs", False) else ""
                })

        schema_dict["sources"].append(source_block)

        # --- Write schema.yml (if enabled) ---
        if spec.get("generate_model_schema_yml", False):
            schema_file = os.path.join(settings.DBT_MODELS_PATH, "schema.yml")
            with open(schema_file, "w") as f:
                yaml.dump(schema_dict, f, sort_keys=False)
            previews[schema_file] = yaml.dump(schema_dict, sort_keys=False)

        return {"message": "✅ dbt models and schema.yml generated successfully.", "previews": previews}

    except Exception as e:
        return {"message": f"❌ Failed to generate dbt files: {str(e)}", "previews": {}}

def ensure_dirs() -> None:
    # Remove everything inside DBT_MODELS_PATH
    if os.path.exists(DBT_MODELS_PATH):
        shutil.rmtree(DBT_MODELS_PATH)

    # Recreate base directory
    os.makedirs(DBT_MODELS_PATH, exist_ok=True)

    os.makedirs(os.path.join(settings.DBT_MODELS_PATH, "staging"), exist_ok=True)
    os.makedirs(os.path.join(settings.DBT_MODELS_PATH, "marts"), exist_ok=True)

def safe_materialization(mat: str, default: str) -> str:
    valid = getattr(settings, "VALID_MATERIALIZATIONS", {"view", "table", "incremental"})
    return mat if mat in valid else default

def materialization_block(mat: str) -> str:
    smat = safe_materialization(mat, settings.DEFAULT_STAGING_MATERIALIZATION)
    return f"{{{{ config(materialized='{smat}') }}}}\n"

def staging_sql(table: TableSpec, source_name: str, options: GenerationOptions) -> str:
    cols = []
    for c in table.columns:
        if c.name == "id":
            cols.append(f"    id as {table.name}_id")
        elif c.name == "user_id":
            cols.append("    user_id as customer_id")
        else:
            cols.append(f"    {c.name}")
    return (
            materialization_block(options.staging_materialization)
            + "select\n"
            + ",\n".join(cols)
            + f"\nfrom {{{{ source('{source_name}', '{table.name}') }}}}"
    )

def dbt_run(cmd: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    """
    Run a dbt command and capture output.
    """
    timeout = timeout or settings.DBT_TIMEOUT_SEC
    cwd = settings.DBT_PROJECT_PATH
    try:
        proc = subprocess.run(["dbt"] + cmd, cwd=cwd,
                              capture_output=True, text=True, timeout=timeout)
        return {"returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr}
    except FileNotFoundError:
        proc = subprocess.run(["python", "-m", "dbt"] + cmd, cwd=cwd,
                              capture_output=True, text=True, timeout=timeout)
        return {"returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr}
# ---------------- Endpoints ----------------

@app.post("/generate_from_spec")
def generate_from_spec(payload: InteractivePayload):

    spec = payload.spec
    options = payload.options

    if not settings.USE_GOOGLE_AI and not settings.OLLAMA_ENABLED:
       return generate_dbt_files(payload)

    ensure_dirs()

    results = {}

    # Write source schema YAML if requested
    if spec.generate_model_schema_yml:
        schema_path = write_source_schema(spec)
        results["schema_yml"] = schema_path

    for t in spec.tables:
        stg_name = f"{options.naming_convention_staging_prefix}{t.name}"
        deterministic_sql = staging_sql(t, spec.source_name, options)

        # Try AI (Google or Ollama)
        ai_sql = ""
        prompt = build_dbt_prompt(spec, t, options)
        if settings.USE_GOOGLE_AI:
            candidate_sql = call_google_ai_studio(prompt)
        else:
            candidate_sql = call_ollama(prompt, stream=False)

        candidate_sql = clean_ai_sql(candidate_sql)
        if validate_sql(candidate_sql):
            ai_sql = candidate_sql
            path_ai = os.path.join(settings.DBT_MODELS_PATH, "staging", f"{stg_name}_ai.sql")
            with open(path_ai, "w", encoding="utf-8") as f:
                f.write(ai_sql)
        else:
            logging.warning(f"AI suggestion invalid for {t.name}, falling back to deterministic SQL.")

        # Always write deterministic SQL
        path_det = os.path.join(settings.DBT_MODELS_PATH, "staging", f"{stg_name}.sql")
        with open(path_det, "w", encoding="utf-8") as f:
            f.write(deterministic_sql)

        results[t.name] = {"deterministic": path_det, "ai": ai_sql}

        # ✅ Generate mart SQL if requested
        if spec.generate_marts:
            mart_name = f"{t.name}{options.naming_convention_mart_suffix}"
            path_mart = os.path.join(settings.DBT_MODELS_PATH, "marts", f"{mart_name}.sql")
            with open(path_mart, "w", encoding="utf-8") as f:
                f.write(mart_sql(t, options))
            results[t.name]["mart"] = path_mart

    return results

@app.post("/preview_from_spec")
def preview_from_spec(payload: InteractivePayload):
    """
    Preview SQL generation without writing files.
    Returns deterministic SQL and optional AI SQL for each table.
    """
    spec = payload.spec
    options = payload.options
    previews = {}
    if not settings.USE_GOOGLE_AI and not settings.OLLAMA_ENABLED:
        return generate_dbt_files(payload)

    for t in spec.tables:
        deterministic_sql = staging_sql(t, spec.source_name, options)

        ai_sql = ""
        prompt = build_dbt_prompt(spec, t, options)
        if settings.USE_GOOGLE_AI:
            candidate_sql = call_google_ai_studio(prompt)
        else:
            candidate_sql = call_ollama(prompt, stream=False)
        candidate_sql = clean_ai_sql(candidate_sql)

        if validate_sql(candidate_sql):
            ai_sql = candidate_sql
        else:
            logging.warning(f"AI suggestion invalid for {t.name}, falling back to deterministic only.")

        # Add mart preview if requested
        mart_preview = None
        if spec.generate_marts:
            mart_preview = mart_sql(t, options)

        previews[t.name] = {
            "deterministic": deterministic_sql,
            "ai": ai_sql,
            "mart": mart_preview
        }

    # Add source schema preview if requested
    if spec.generate_model_schema_yml:
        source_def = {
            "version": 2,
            "sources": [
                {
                    "name": spec.source_name,
                    "database": spec.database,
                    "schema": spec.schema_name,
                    "tables": [
                        {
                            "name": t.name,
                            "description": t.description or "",
                            "columns": [
                                {"name": c.name, "description": c.description or ""}
                                for c in t.columns
                            ],
                        }
                        for t in spec.tables
                    ],
                }
            ],
        }
        previews["schema_yml"] = yaml.dump(source_def, sort_keys=False)

    return previews

@app.post("/build")
def dbt_build():
    """
    Run dbt build (compile, run, and test).
    """
    result = dbt_run(["build"])
    return result

@app.post("/test")
def dbt_test():
    """
    Run dbt test only.
    """
    result = dbt_run(["test"])
    return result
