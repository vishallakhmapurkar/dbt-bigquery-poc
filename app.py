from fastapi import  UploadFile, Form, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
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
from settings import REPO_PATH,DBT_MODELS_PATH, DBT_PROJECT_PATH
import settings
import shutil

app = FastAPI(title="dbt>Gen Backend")

# CORS (if serving frontend separately; safe to leave enabled)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def count_model_files():
    counts = {"staging": 0, "mart": 0, "schema": 0}
    for root, _, files in os.walk(DBT_MODELS_PATH):
        for file in files:
            if file.endswith(".sql"):
                if "staging" in root.lower() or "staging" in file.lower():
                    counts["staging"] += 1
                elif "marts" in root.lower() or "marts" in file.lower():
                    counts["mart"] += 1
            elif file.endswith((".yml", ".yaml")):
                counts["schema"] += 1
    return counts

@app.get("/api/fileCounts")
async def file_counts():
    return JSONResponse(content=count_model_files())

def build_dbt_prompt(spec: Dict[str, Any], table: Dict[str, Any], options: Dict[str, Any]) -> str:
    """
    Build a dbt SQL generation prompt using JSON metadata.
    Ensures BigQuery-friendly syntax and proper dbt conventions.
    """
    # Collect column details
    column_details = []
    for c in table.get("columns", []):
        col_desc = c.get("description", "")
        col_type = c.get("type", "")
        detail = f"{c['name']} ({col_type}) - {col_desc}" if col_desc or col_type else c["name"]
        column_details.append(detail)

    # Join into readable list
    column_list = "\n".join([f"- {d}" for d in column_details]) or "No columns provided"
    desc = table.get("description", "No description provided")

    # Use primary key if available
    pk = table.get("primary_key")

    return f"""You are a SQL generator for dbt models targeting BigQuery.

Project Context:
- Source: {spec.get('source_name')}
- Database: {spec.get('database', 'default_db')}
- Schema: {spec.get('schema_name', 'default_schema')}
- Table: {table.get('name')}
- Table Description: {desc}

Columns (use only these, in order):
{column_list}

Requirements:
1. Use BigQuery **standard SQL** syntax.
2. **Always start the model with a config block**:
   {{ config(materialized='{options.get('staging_materialization','view')}') }}
3. Select from the dbt source macro:
   {{ source('{spec.get('source_name')}', '{table.get('name')}') }}
4. Apply naming conventions:
   - Treat the declared primary key `{pk}` as the identifier column.
   - Alias it as `{table.get('name')}_id` for consistency.
   - Keep all other columns unchanged.
5. Preserve column order exactly as in the JSON spec.
6. Include explicit column aliases identical to the original names (except the primary key alias).
7. Output **only valid SQL code**, no commentary, markdown fences, or explanations.
"""




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
    return sql_text.replace("```sql", "").replace("```", "").strip()

def call_google_ai_studio(prompt: str, model: str = "models/gemini-2.5-flash") -> str:
    if not settings.GOOGLE_API_KEY:
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

def mart_sql(table: Dict[str, Any], options: Dict[str, Any]) -> str:
    return (
            materialization_block(options.get("mart_materialization", "table"))
            + f"select * from {{{{ ref('{options.get('naming_convention_staging_prefix','stg_')}{table['name']}') }}}}"
    )

def staging_sql(table: Dict[str, Any], source_name: str, options: Dict[str, Any]) -> str:
    cols = []
    for c in table.get("columns", []):
        if c["name"] == "id":
            cols.append(f"    id as {table['name']}_id")
        elif c["name"] == "user_id":
            cols.append("    user_id as customer_id")
        else:
            cols.append(f"    {c['name']}")
    return (
            materialization_block(options.get("staging_materialization", "view"))
            + "select\n"
            + ",\n".join(cols)
            + f"\nfrom {{{{ source('{source_name}', '{table['name']}') }}}}"
    )
def write_source_schema(spec: Dict[str, Any]) -> str:
    path = os.path.join(settings.DBT_PROJECT_PATH, "models", "schema.yml")
    source_def = {
        "version": 2,
        "sources": [
            {
                "name": spec.get("source_name"),
                "database": spec.get("database"),
                "schema": spec.get("schema_name"),
                "tables": [
                    {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "columns": [
                            {"name": c["name"], "description": c.get("description", "")}
                            for c in t.get("columns", [])
                        ],
                    }
                    for t in spec.get("tables", [])
                ],
            }
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(source_def, f, sort_keys=False)
    return path
def validate_sql(sql_text: str) -> bool:
    if not sql_text or not sql_text.strip():
        logging.warning("AI suggestion invalid for %s: empty SQL", sql_text)
        return False

    if "```" in sql_text:
        logging.warning("AI suggestion invalid for %s: contains markdown fences", sql_text)
        return False

    # Normalize for case/spacing
    normalized = sql_text.lower()

    if "{{ source(" not in normalized and "{{ ref(" not in normalized:
        logging.warning("AI suggestion invalid for %s: missing source/ref macro", sql_text)
        return False

    if "{{ config(" not in normalized:
        logging.warning("AI suggestion invalid for %s: missing config macro", sql_text)
        return False

    # Passed all checks
    return True
def generate_dbt_files(spec_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate dbt models (staging + marts) and per-model schema.yml files.
    Global schema.yml will only contain sources (no models).
    Returns previews of all generated files.
    """
    try:
        # Normalize input
        if isinstance(spec_json, str):
            spec_json = json.loads(spec_json)
        elif hasattr(spec_json, "dict"):
            spec_json = spec_json.dict()
        elif hasattr(spec_json, "__dict__"):
            spec_json = dict(spec_json.__dict__)

        spec = spec_json.get("spec", {})
        options = spec_json.get("options", {})

        source_name = spec.get("source_name")

        # --- Ensure base directories exist ---
        ensure_dirs()

        # --- Global schema.yml (sources only) ---
        global_schema_dict = {"version": 2, "sources": []}
        source_block = {"name": source_name, "schema": spec.get("schema", source_name), "tables": []}

        previews: Dict[str, str] = {}

        # --- Process each table ---
        for table in spec.get("tables", []):
            table_name = table["name"]
            columns = table["columns"]

            # Build SELECT statement for staging
            select_columns = ",\n    ".join([f"{col['name']} AS {col['name']}" for col in columns])

            # --- Staging model SQL ---
            staging_model_name = f"{options.get('naming_convention_staging_prefix', 'stg_')}{table_name}"
            staging_sql_text = f"""
{{{{ config(materialized='{options.get('staging_materialization', 'view')}') }}}}

SELECT
    {select_columns}
FROM {{{{ source('{source_name}', '{table_name}') }}}}
"""
            staging_file = os.path.join(settings.DBT_MODELS_PATH, "staging", f"{staging_model_name}.sql")
            with open(staging_file, "w", encoding="utf-8") as f:
                f.write(staging_sql_text.strip())
            previews[staging_file] = staging_sql_text.strip()

            # --- Staging schema.yml ---
            staging_schema = {
                "version": 2,
                "models": [{
                    "name": staging_model_name,
                    "description": f"Staging model for {table_name}" if options.get("include_docs", False) else "",
                    "columns": [
                        {
                            "name": col["name"],
                            "description": col.get("description", "") if options.get("include_docs", False) else ""
                        }
                        for col in columns
                    ]
                }]
            }
            staging_schema_file = os.path.join(settings.DBT_MODELS_PATH, "staging", f"{staging_model_name}.yml")
            with open(staging_schema_file, "w", encoding="utf-8") as f:
                yaml.dump(staging_schema, f, sort_keys=False)
            previews[staging_schema_file] = yaml.dump(staging_schema, sort_keys=False)

            # --- Mart model SQL + schema.yml ---
            if spec.get("generate_marts", False):
                mart_model_name = f"{table_name}{options.get('naming_convention_mart_suffix', '_mart')}"
                marts_sql = f"""
{{{{ config(materialized='{options.get('mart_materialization', 'table')}') }}}}

SELECT
    *
FROM {{{{ ref('{staging_model_name}') }}}}
"""
                marts_file = os.path.join(settings.DBT_MODELS_PATH, "marts", f"{mart_model_name}.sql")
                with open(marts_file, "w", encoding="utf-8") as f:
                    f.write(marts_sql.strip())
                previews[marts_file] = marts_sql.strip()

                # Mart schema.yml
                mart_schema = {
                    "version": 2,
                    "models": [{
                        "name": mart_model_name,
                        "description": f"Mart model for {table_name}" if options.get("include_docs", False) else "",
                        "columns": [
                            {
                                "name": col["name"],
                                "description": col.get("description", "") if options.get("include_docs", False) else ""
                            }
                            for col in columns
                        ]
                    }]
                }
                mart_schema_file = os.path.join(settings.DBT_MODELS_PATH, "marts", f"{mart_model_name}.yml")
                with open(mart_schema_file, "w", encoding="utf-8") as f:
                    yaml.dump(mart_schema, f, sort_keys=False)
                previews[mart_schema_file] = yaml.dump(mart_schema, sort_keys=False)

            # --- Update global sources only ---
            table_entry = {"name": table_name}
            if options.get("include_docs", False):
                table_entry["description"] = table.get("description", "")
            source_block["tables"].append(table_entry)

        global_schema_dict["sources"].append(source_block)

        # --- Write global schema.yml (sources only) ---
        if spec.get("generate_model_schema_yml", False):
            schema_file = os.path.join(settings.DBT_MODELS_PATH, "schema.yml")
            with open(schema_file, "w", encoding="utf-8") as f:
                yaml.dump(global_schema_dict, f, sort_keys=False)
            previews[schema_file] = yaml.dump(global_schema_dict, sort_keys=False)

        return {"message": "✅ dbt models and per-model schema.yml files generated successfully.", "previews": previews}

    except Exception as e:
        logging.error(f"generate_dbt_files failed: {e}")
        return {"message": f"❌ Failed to generate dbt files: {str(e)}", "previews": {}}

# ---------------- Endpoints ----------------
# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("index.html")


# -------------------- Endpoints --------------------

@app.post("/upload_spec")
async def upload_spec(file: UploadFile):
    try:
        content = await file.read()
        parsed = json.loads(content.decode("utf-8"))
        spec = parsed.get("spec", {})
        if not spec:
            return JSONResponse({"error": "Missing key 'spec' in JSON"}, status_code=400)

        tables = [t.get("name") for t in spec.get("tables", [])]
        source = spec.get("source_name")
        return JSONResponse({
            "message": "Spec uploaded successfully",
            "source": source,
            "tables": tables,
            "raw": spec
        })
    except Exception as e:
        return JSONResponse({"error": f"Failed to parse JSON: {str(e)}"}, status_code=400)


@app.post("/save_config")
async def save_config(
        staging_mat: str = Form(...),
        mart_mat: str = Form(...),
        stg_prefix: str = Form(...),
        mart_suffix: str = Form(...)
):
    payload = {
        "options": {
            "staging_materialization": staging_mat,
            "mart_materialization": mart_mat,
            "naming_convention_staging_prefix": stg_prefix,
            "naming_convention_mart_suffix": mart_suffix,
            "include_docs": True,
            "include_tests": False
        }
    }
    return JSONResponse({"message": "Configuration saved", "payload": payload})


@app.post("/preview_from_spec")
async def preview_from_spec(request: Request):
    """
    Preview SQL generation without writing files.
    Returns deterministic SQL and optional AI SQL for each table.
    """
    try:
        payload = await request.json()
        spec: Dict[str, Any] = payload.get("spec", {})
        options: Dict[str, Any] = payload.get("options", {})
        previews: Dict[str, Any] = {}

        # If no AI enabled, fall back to deterministic generator
        if not settings.USE_GOOGLE_AI and not settings.OLLAMA_ENABLED:
            return JSONResponse(generate_dbt_files(payload))

        for t in spec.get("tables", []):
            # Deterministic SQL
            deterministic_sql = staging_sql(t, spec.get("source_name"), options)

            # AI SQL
            ai_sql = ""
            prompt = build_dbt_prompt(spec, t, options)
            if settings.USE_GOOGLE_AI:
                candidate_sql = call_google_ai_studio(prompt)
            elif settings.OLLAMA_ENABLED:
                candidate_sql = call_ollama(prompt, stream=False)
            else:
                candidate_sql = ""

            candidate_sql = clean_ai_sql(candidate_sql)
            if validate_sql(candidate_sql):
                ai_sql = candidate_sql
            else:
                logging.warning(f"AI suggestion invalid for {t.get('name')}, falling back to deterministic only.")

            # Mart preview if requested
            mart_preview = None
            if spec.get("generate_marts", False):
                mart_preview = mart_sql(t, options)

            previews[t["name"]] = {
                "deterministic": deterministic_sql,
                "ai": ai_sql,
                "mart": mart_preview
            }

        # Schema preview if requested
        if spec.get("generate_model_schema_yml", False):
            source_def = {
                "version": 2,
                "sources": [
                    {
                        "name": spec.get("source_name"),
                        "database": spec.get("database"),
                        "schema": spec.get("schema_name"),
                        "tables": [
                            {
                                "name": t["name"],
                                "description": t.get("description", ""),
                                "columns": [
                                    {"name": c["name"], "description": c.get("description", "")}
                                    for c in t.get("columns", [])
                                ],
                            }
                            for t in spec.get("tables", [])
                        ],
                    }
                ],
            }
            previews["schema_yml"] = yaml.dump(source_def, sort_keys=False)

        return JSONResponse({"message": "Preview generated", "previews": previews})

    except Exception as e:
        logging.error(f"Preview failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)

def dbt_run(cmd: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    """
    Run a dbt command and capture output in a structured way.
    Supports both `dbt` CLI and fallback to `python -m dbt`.
    """
    # Resolve timeout
    effective_timeout = timeout or settings.DBT_TIMEOUT_SEC
    cwd = settings.DBT_PROJECT_PATH

    def _run(command: List[str]) -> Dict[str, Any]:
        try:
            proc = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=effective_timeout
            )
            return {
                "command": " ".join(command),
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "success": proc.returncode == 0,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "command": " ".join(command),
                "returncode": -1,
                "stdout": e.stdout or "",
                "stderr": f"Timeout after {effective_timeout}s\n{e.stderr or ''}",
                "success": False,
            }

    # Try native dbt first
    result = _run(["dbt"] + cmd)
    if result["returncode"] == 127 or "not found" in result["stderr"].lower():
        # Fallback to python -m dbt
        result = _run(["python", "-m", "dbt"] + cmd)

    return result

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
@app.post("/generate_from_spec")
async def generate_from_spec(request: Request):
    """
    Generate dbt models (staging + marts) and per-model schema.yml files.
    Uses AI (Google or Ollama) if enabled, otherwise falls back to deterministic SQL.
    """
    try:
        payload = await request.json()
        spec = payload.get("spec")
        options = payload.get("options")

        # If no AI enabled, use deterministic generator
        if not settings.USE_GOOGLE_AI and not settings.OLLAMA_ENABLED:
            return JSONResponse(generate_dbt_files(payload))

        ensure_dirs()
        results: Dict[str, Any] = {}

        # Write source schema YAML if requested
        if spec.get("generate_model_schema_yml", False):
            schema_path = write_source_schema(spec)
            results["schema_yml"] = schema_path

        for t in spec.get("tables", []):
            stg_name = f"{options.get('naming_convention_staging_prefix','stg_')}{t['name']}"
            deterministic_sql = staging_sql(t, spec["source_name"], options)

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
                logging.warning(f"AI suggestion invalid for {t['name']}, falling back to deterministic SQL.")

            # Always write deterministic SQL
            path_det = os.path.join(settings.DBT_MODELS_PATH, "staging", f"{stg_name}.sql")
            with open(path_det, "w", encoding="utf-8") as f:
                f.write(deterministic_sql)

            results[t["name"]] = {"deterministic": path_det, "ai": ai_sql}

            # ✅ Generate mart SQL if requested
            if spec.get("generate_marts", False):
                mart_name = f"{t['name']}{options.get('naming_convention_mart_suffix','_mart')}"
                path_mart = os.path.join(settings.DBT_MODELS_PATH, "marts", f"{mart_name}.sql")
                with open(path_mart, "w", encoding="utf-8") as f:
                    f.write(mart_sql(t, options))
                results[t["name"]]["mart"] = path_mart

        return JSONResponse({"message": "Files generated", "results": results})

    except Exception as e:
        logging.error(f"Generate failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)

@app.post("/build")
async def build():
    try:
        proc = dbt_run(["build"])
        return JSONResponse(proc)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/test")
async def test():
    try:
        proc = dbt_run(["test"])
        return JSONResponse(proc)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/gitpush")
async def gitpush(commit_msg: str = Form(...)):
    if not commit_msg.strip():
        return JSONResponse({"error": "Commit message required"}, status_code=400)
    try:
        cmds = [
            ["git", "-C", REPO_PATH, "add", "."],
            ["git", "-C", REPO_PATH, "commit", "-m", commit_msg],
            ["git", "-C", REPO_PATH, "push"]
        ]
        logs = ""
        for cmd in cmds:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            logs += f"$ {' '.join(cmd)}\n{proc.stdout}{proc.stderr}\n"
            if proc.returncode != 0:
                return JSONResponse({"error": "Git command failed", "logs": logs}, status_code=400)
        return JSONResponse({"message": "Git push successful", "logs": logs})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
