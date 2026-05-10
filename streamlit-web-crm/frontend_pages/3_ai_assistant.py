import streamlit as st
import sqlite3
import os
import re
import time
import requests
import pandas as pd
import anthropic

# ── DB path ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'backend_crm', 'db.sqlite3')

# ── Schema description fed to the LLM ────────────────────────────────────────
SCHEMA_DESCRIPTION = """
You are an expert CRM data analyst. The database is SQLite and contains these tables:

1. crm_model_customerprofile
   - customer_id (INTEGER, PK)
   - first_name (TEXT)
   - last_name (TEXT)
   - gender (TEXT)
   - date_of_birth (DATETIME)
   - email (TEXT, unique)
   - phone_number (TEXT, unique)
   - signup_date (DATETIME)
   - address (TEXT)
   - city (TEXT)
   - state (TEXT)
   - zip_code (TEXT)
   - is_active (BOOLEAN)

2. crm_model_product
   - product_id (INTEGER, PK)
   - product_name (TEXT)
   - category (TEXT)
   - price_per_unit (DECIMAL)
   - brand (TEXT)
   - product_description (TEXT)

3. crm_model_purchasehistory
   - purchase_id (INTEGER, PK)
   - customer_id (INTEGER, FK → crm_model_customerprofile)
   - product_id (INTEGER, FK → crm_model_product)
   - purchase_date (DATETIME)
   - quantity (INTEGER)
   - total_amount (DECIMAL)

4. crm_model_customersegment
   - id (INTEGER, PK)
   - customer_id (INTEGER, FK → crm_model_customerprofile, unique)
   - recency_days (INTEGER)  -- days since last purchase (lower = more recent)
   - frequency (INTEGER)     -- number of distinct purchase dates
   - monetary (DECIMAL)      -- total amount spent
   - r_score (INTEGER, 1-5)
   - f_score (INTEGER, 1-5)
   - m_score (INTEGER, 1-5)
   - rfm_score (INTEGER)     -- r_score*100 + f_score*10 + m_score
   - segment (TEXT)          -- Champion / Loyal / At Risk / Hibernating
   - last_calculated (DATETIME)

Rules:
- Always use table aliases for clarity.
- Use SQLite-compatible syntax (strftime for dates, etc.).
- For questions about customers joining / purchasing, use appropriate JOINs.
- Return ONLY the raw SQL query when asked to generate SQL, with no markdown fences.
- When answering a question, first show the SQL you executed, then present the result in plain language.
"""

SYSTEM_PROMPT = SCHEMA_DESCRIPTION + """
When the user asks a question about the CRM data:
1. Generate the SQLite SQL query required to answer it.
2. Return a JSON-like structured response in this EXACT format (no markdown fences):

SQL:
<the sql query here>

ANSWER:
<plain-language answer here, including key numbers/findings>

If the user is asking a general question (not about data), just answer naturally without SQL.
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def run_query(sql: str) -> tuple[list[dict], str | None]:
    """Execute a SELECT query and return (rows, error)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows, None
    except Exception as e:
        return [], str(e)


def extract_sql(text: str) -> str | None:
    """Extract SQL from the LLM response."""
    match = re.search(r"SQL:\s*\n(.*?)(?=\nANSWER:|\Z)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # fallback: try to find a SELECT statement anywhere
    select_match = re.search(r"(SELECT\s+.+?;)", text, re.DOTALL | re.IGNORECASE)
    if select_match:
        return select_match.group(1).strip()
    return None


def extract_answer(text: str) -> str:
    """Extract the plain-language answer from the LLM response."""
    match = re.search(r"ANSWER:\s*\n(.*)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def fetch_gateway_token(keycloak_url: str, x_api_key: str, client_secret: str,
                         username: str, password: str) -> tuple[str, str | None]:
    """Authenticate against Keycloak using OAuth2 Resource Owner Password Credentials grant.

    Returns (access_token, error).
    """
    try:
        resp = requests.post(
            keycloak_url,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "x-api-key": x_api_key,
            },
            data={
                "client_id": "BackendAPI",
                "client_secret": client_secret,
                "grant_type": "password",
                "scope": "openid",
                "username": username,
                "password": password,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            return "", f"No access_token in response: {resp.json()}"
        return token, None
    except requests.HTTPError as e:
        return "", f"Auth failed ({e.response.status_code}): {e.response.text}"
    except Exception as e:
        return "", str(e)


def call_llm(access_token: str, messages: list[dict]) -> str:
    """POST a chat request to the company LLM gateway (Bedrock/Claude via proxy).

    Uses the exact payload structure required by the gateway.
    """
    gateway_url = st.session_state.get("gateway_url", "").strip()
    model_name = st.session_state.get("model_name", "claude-sonnet-4-5").strip() or "claude-sonnet-4-5"

    # Convert messages to Bedrock converse format
    bedrock_msgs = [
        {"role": m["role"], "content": [{"text": m["content"]}]}
        for m in messages
    ]
    payload = {
        "method": "POST",
        "llm_provider": "bedrock",
        "llm_model": model_name,
        "action": "converse",
        "stream": False,
        "llm_payload": {
            "system": [{"text": SYSTEM_PROMPT}],
            "messages": bedrock_msgs,
            "inferenceConfig": {"temperature": 0.1, "maxTokens": 2048},
        },
    }
    resp = requests.post(
        gateway_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["output"]["message"]["content"][0]["text"]


def ask_claude(messages: list[dict]) -> str:
    """Dispatch to company gateway or direct Anthropic API depending on mode."""

    # ── Gateway mode ──────────────────────────────────────────────────────────
    if st.session_state.get("gateway_url"):
        token = st.session_state.get("gateway_bearer_token", "")
        if not token:
            return "⚠️ Not authenticated. Click **Get Token** in the sidebar first."
        try:
            return call_llm(token, messages)
        except requests.HTTPError as e:
            return f"⚠️ Gateway error ({e.response.status_code}): {e.response.text}"
        except Exception as e:
            return f"⚠️ Error calling gateway: {e}"

    # ── Direct Anthropic API mode ─────────────────────────────────────────────
    api_key = st.session_state.get("anthropic_api_key", "")
    if not api_key:
        return "⚠️ Please enter your Anthropic API key in the sidebar."

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=st.session_state.get("model_name", "claude-sonnet-4-5") or "claude-sonnet-4-5",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text


# ── Page ──────────────────────────────────────────────────────────────────────

st.title("🤖 CRM AI Assistant")
st.caption("Ask questions about your CRM data in plain English. Powered by Claude.")

st.markdown("""
Welcome to the **CRM AI Assistant** — your intelligent assistant for exploring and understanding your customer data.
Instead of writing complex database queries, you can simply ask questions in plain English such as
*"Who are our top 10 customers by revenue?"* or *"How many customers are in the Champion segment?"*.
The chatbot automatically translates your question into a SQL query, runs it against the live CRM database,
and returns a clear, concise answer along with the underlying data.

This tool is designed to help sales, marketing, and operations teams quickly surface insights from customer
profiles, purchase history, product performance, and RFM segmentation — without any technical expertise required.
""")

# Sidebar – connection settings
with st.sidebar:
    st.header("⚙️ Settings")

    st.subheader("🔌 LLM Connection")
    use_gateway = st.toggle("Use Company LLM Gateway", value=bool(st.session_state.get("gateway_url")))

    if use_gateway:
        gateway_input = st.text_input(
            "Gateway URL",
            value=st.session_state.get("gateway_url", ""),
            placeholder="https://llm-gateway.yourcompany.com/api/llm",
            help="The POST endpoint for LLM chat requests.",
        )
        if gateway_input:
            st.session_state["gateway_url"] = gateway_input.strip()
        elif "gateway_url" in st.session_state:
            del st.session_state["gateway_url"]

        keycloak_input = st.text_input(
            "Keycloak Token URL",
            value=st.session_state.get("keycloak_url", ""),
            placeholder="https://auth.yourcompany.com/realms/myrealm/protocol/openid-connect/token",
            help="OAuth2 token endpoint (grant_type=password).",
        )
        if keycloak_input:
            st.session_state["keycloak_url"] = keycloak_input.strip()

        x_api_key_input = st.text_input(
            "x-api-key",
            value=st.session_state.get("x_api_key", ""),
            placeholder="Gateway x-api-key header value",
        )
        if x_api_key_input:
            st.session_state["x_api_key"] = x_api_key_input.strip()

        client_secret_input = st.text_input(
            "Client Secret",
            type="password",
            placeholder="Keycloak client_secret for BackendAPI",
        )
        if client_secret_input:
            st.session_state["client_secret"] = client_secret_input

        username_input = st.text_input(
            "Username",
            value=st.session_state.get("gw_username", ""),
            placeholder="your.name@company.com",
        )
        if username_input:
            st.session_state["gw_username"] = username_input

        password_input = st.text_input(
            "Password",
            type="password",
            placeholder="••••••••",
        )
        if password_input:
            st.session_state["gw_password"] = password_input

        model_input = st.text_input(
            "Model Name",
            value=st.session_state.get("model_name", "claude-sonnet-4-5"),
            placeholder="e.g. anthropic.claude-sonnet-4-5-v1:0",
            help="Model identifier passed as llm_model in the gateway payload.",
        )
        st.session_state["model_name"] = model_input or "claude-sonnet-4-5"

        # Authenticate button
        if st.button("🔑 Get Token", use_container_width=True):
            _keycloak = st.session_state.get("keycloak_url", "")
            _x_api_key = st.session_state.get("x_api_key", "")
            _client_secret = st.session_state.get("client_secret", "")
            _user = st.session_state.get("gw_username", "")
            _pass = st.session_state.get("gw_password", "")
            if not all([_keycloak, _x_api_key, _client_secret, _user, _pass]):
                st.error("Please fill in all fields: Keycloak URL, x-api-key, Client Secret, Username and Password.")
            else:
                with st.spinner("Authenticating with Keycloak…"):
                    tok, err = fetch_gateway_token(_keycloak, _x_api_key, _client_secret, _user, _pass)
                if err:
                    st.error(f"Authentication failed: {err}")
                    st.session_state.pop("gateway_bearer_token", None)
                else:
                    st.session_state["gateway_bearer_token"] = tok
                    st.session_state["gateway_token_time"] = time.time()
                    st.success("✅ Token obtained successfully!")

        # Token status
        if st.session_state.get("gateway_bearer_token"):
            age_min = (time.time() - st.session_state.get("gateway_token_time", 0)) / 60
            st.success(f"✅ Authenticated · token age: {age_min:.0f} min")
            if st.button("🔄 Refresh Token", use_container_width=True):
                st.session_state.pop("gateway_bearer_token", None)
                st.rerun()
        else:
            st.warning("⚠️ Not authenticated — click Get Token")

    else:
        # Clear gateway state when switching back to direct mode
        for k in ("gateway_url", "gateway_bearer_token", "keycloak_url",
                  "x_api_key", "client_secret", "gw_username", "gw_password"):
            st.session_state.pop(k, None)

        api_key_input = st.text_input(
            "Anthropic API Key",
            type="password",
            placeholder="sk-ant-...",
            help="Get your key at https://console.anthropic.com/",
        )
        if api_key_input:
            st.session_state["anthropic_api_key"] = api_key_input

        model_input = st.text_input(
            "Model Name",
            value=st.session_state.get("model_name", "claude-sonnet-4-5"),
            placeholder="claude-sonnet-4-5",
        )
        st.session_state["model_name"] = model_input or "claude-sonnet-4-5"

        if st.session_state.get("anthropic_api_key"):
            st.success("✅ Direct Anthropic API")
        else:
            st.warning("⚠️ API key not set")

    st.divider()
    st.subheader("📋 Schema Reference")
    with st.expander("Tables & Columns"):
        st.markdown("""
**crm_model_customerprofile**
`customer_id`, `first_name`, `last_name`, `gender`, `date_of_birth`, `email`, `phone_number`, `signup_date`, `address`, `city`, `state`, `zip_code`, `is_active`

**crm_model_product**
`product_id`, `product_name`, `category`, `price_per_unit`, `brand`

**crm_model_purchasehistory**
`purchase_id`, `customer_id`, `product_id`, `purchase_date`, `quantity`, `total_amount`

**crm_model_customersegment**
`customer_id`, `recency_days`, `frequency`, `monetary`, `r_score`, `f_score`, `m_score`, `rfm_score`, `segment`
        """)

    st.divider()
    if st.button("🗑️ Clear Chat"):
        st.session_state["chat_history"] = []
        st.session_state["llm_messages"] = []
        st.rerun()

# Example questions
with st.expander("💡 Example questions", expanded=False):
    examples = [
        "How many active customers do we have?",
        "Who are the top 10 customers by total spending?",
        "What are the best-selling product categories?",
        "Show me all Champion segment customers.",
        "How many purchases were made in 2023?",
        "What is the average order value per customer segment?",
        "List customers who have not purchased in the last 180 days.",
        "Which city has the most customers?",
    ]
    cols = st.columns(2)
    for i, ex in enumerate(examples):
        if cols[i % 2].button(ex, key=f"ex_{i}"):
            st.session_state["pending_question"] = ex

# Initialize chat state
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "llm_messages" not in st.session_state:
    st.session_state["llm_messages"] = []

# Display chat history
for msg in st.session_state["chat_history"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sql"):
            with st.expander("🔍 SQL Query"):
                st.code(msg["sql"], language="sql")
        if msg.get("data") is not None:
            import pandas as pd
            df = pd.DataFrame(msg["data"])
            if not df.empty:
                with st.expander(f"📊 Query Results ({len(df)} rows)"):
                    st.dataframe(df, use_container_width=True)

# Handle pending question from example buttons
if "pending_question" in st.session_state:
    user_input = st.session_state.pop("pending_question")
else:
    user_input = st.chat_input("Ask a question about your CRM data…")

if user_input:
    # Display user message
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state["chat_history"].append({"role": "user", "content": user_input})
    st.session_state["llm_messages"].append({"role": "user", "content": user_input})

    # Get Claude response
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            raw_reply = ask_claude(st.session_state["llm_messages"])

        sql = extract_sql(raw_reply)
        answer = extract_answer(raw_reply)
        query_rows = None
        db_error = None

        # Execute the SQL if one was generated
        if sql:
            query_rows, db_error = run_query(sql)

        # Build the displayed answer
        if db_error:
            display_answer = (
                f"{answer}\n\n"
                f"⚠️ **SQL execution error:** `{db_error}`\n\n"
                "The query above may need adjustment for your specific data."
            )
        else:
            display_answer = answer

        st.markdown(display_answer)

        if sql:
            with st.expander("🔍 SQL Query"):
                st.code(sql, language="sql")

        if query_rows is not None and not db_error:
            df = pd.DataFrame(query_rows)
            if not df.empty:
                with st.expander(f"📊 Query Results ({len(df)} rows)"):
                    st.dataframe(df, use_container_width=True)

    # Persist to session state
    st.session_state["chat_history"].append({
        "role": "assistant",
        "content": display_answer,
        "sql": sql,
        "data": query_rows if not db_error else None,
    })
    st.session_state["llm_messages"].append({"role": "assistant", "content": raw_reply})
