"""
🌊 AquaGuard Agent — Main Application Dashboard
Multi-Agent Water Quality Monitoring & Predictive Health Protection System
Built with Google ADK, Gemini, and Gradio.
"""

import os
import asyncio
import warnings
import gradio as gr
from dotenv import load_dotenv

# Import ADK modules
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner

# Import local water analysis tools
from tools.water_analysis_tool import (
    preprocess_data,
    validate_water_sample,
    predict_potability,
    assess_disease_risk,
    get_treatment_recommendations,
    generate_community_report,
)

# Suppress Starlette/Gradio deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*HTTP_422_UNPROCESSABLE_ENTITY.*")

# Load environment variables
load_dotenv()


# ---------------------------------------------------------------------------
# Helper: Read Skill Files (.md)
# ---------------------------------------------------------------------------
def load_skill_instruction(filename: str) -> str:
    """Read the instructions from a skill markdown file."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "skills", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return f"You are a specialist agent named {filename.split('.')[0]}."


# ---------------------------------------------------------------------------
# Multi-Agent Initialization Function
# ---------------------------------------------------------------------------
def initialize_agents(
    project_id: str = None,
    location: str = None,
    credentials_path: str = None,
    api_key: str = None,
) -> tuple[Agent, InMemoryRunner]:
    """
    Initialize all specialist agents and wire them into the Orchestrator.
    Supports Google Cloud Vertex AI or direct Gemini API Key configurations.
    """
    if project_id and location:
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id.strip()
        os.environ["GOOGLE_CLOUD_LOCATION"] = location.strip()
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
        if credentials_path and credentials_path.strip():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path.strip()
        else:
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        os.environ.pop("GEMINI_API_KEY", None)
    elif api_key:
        os.environ["GEMINI_API_KEY"] = api_key.strip()
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
        os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        os.environ.pop("GOOGLE_CLOUD_LOCATION", None)
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

    data_agent = Agent(
        name="data_ingestion_agent",
        description="Handles water data loading, WHO safety range validation, and preprocessing.",
        instruction=load_skill_instruction("data_ingestion_agent.md"),
        model="gemini-2.5-flash",
        tools=[validate_water_sample, preprocess_data],
    )

    prediction_agent = Agent(
        name="prediction_agent",
        description="Forecasts water potability classification and disease risks.",
        instruction=load_skill_instruction("prediction_agent.md"),
        model="gemini-2.5-flash",
        tools=[predict_potability, assess_disease_risk],
    )

    recommendation_agent = Agent(
        name="recommendation_agent",
        description="Generates actionable water treatment suggestions and health guidelines.",
        instruction=load_skill_instruction("recommendation_agent.md"),
        model="gemini-2.5-flash",
        tools=[get_treatment_recommendations],
    )

    education_agent = Agent(
        name="education_agent",
        description="Explains water parameters, disease prevention, and creates community flyers.",
        instruction=load_skill_instruction("education_agent.md"),
        model="gemini-2.5-flash",
        tools=[generate_community_report],
    )

    orchestrator_agent = Agent(
        name="orchestrator_agent",
        description="Central routing and coordination agent for the AquaGuard system.",
        instruction=load_skill_instruction("orchestrator.md"),
        model="gemini-2.5-flash",
        sub_agents=[
            data_agent,
            prediction_agent,
            recommendation_agent,
            education_agent,
        ],
    )

    runner = InMemoryRunner(agent=orchestrator_agent)
    return orchestrator_agent, runner


# ---------------------------------------------------------------------------
# Cached Agent/Runner — avoid re-initializing on every request
# ---------------------------------------------------------------------------
_AGENT_CACHE: dict = {"key": None, "runner": None}


def get_runner(project_id=None, location=None, sa_path=None, api_key=None) -> InMemoryRunner:
    """
    Return a cached InMemoryRunner. Only rebuilds agents when credentials change.
    Saves ~3-5 seconds per request by skipping redundant initialization.
    """
    effective_project_id = (project_id or "").strip() or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    effective_location = (location or "").strip() or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    effective_sa_path = (sa_path or "").strip() or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    effective_api_key = (api_key or "").strip() or os.getenv("GEMINI_API_KEY", "")

    cache_key = (
        effective_project_id,
        effective_location,
        effective_sa_path,
        effective_api_key,
    )

    if _AGENT_CACHE["key"] == cache_key and _AGENT_CACHE["runner"] is not None:
        return _AGENT_CACHE["runner"]

    # Credentials changed — rebuild
    _, runner = initialize_agents(
        effective_project_id,
        effective_location,
        effective_sa_path,
        effective_api_key,
    )
    _AGENT_CACHE["key"] = cache_key
    _AGENT_CACHE["runner"] = runner
    return runner


# ---------------------------------------------------------------------------
# Agent Async Runner Helper
# ---------------------------------------------------------------------------
def extract_text_from_event(event) -> str:
    """Safely extract text content from an ADK Event object."""
    text = ""
    if hasattr(event, "content") and event.content:
        if hasattr(event.content, "parts") and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    text += str(part.text)
        else:
            text += str(event.content)
    elif hasattr(event, "output") and event.output:
        if hasattr(event.output, "text"):
            text += str(event.output.text)
        else:
            text += str(event.output)
    elif hasattr(event, "text") and event.text:
        text += str(event.text)
    elif hasattr(event, "message") and event.message:
        text += str(event.message)
    return text


async def run_agent_workflow(runner: InMemoryRunner, prompt: str) -> str:
    """Async runner execution to accumulate agent output text."""
    try:
        events = await runner.run_debug(prompt)
        output_text = ""
        for event in events:
            output_text += extract_text_from_event(event)

        if not output_text.strip():
            if events:
                last_event = events[-1]
                if hasattr(last_event, "output") and last_event.output:
                    output_text = str(last_event.output)
                else:
                    output_text = "Analysis completed successfully."
            else:
                output_text = "Analysis completed. (Empty response)"
        return output_text
    except Exception as exc:
        return f"⚠️ Error running agent workflow: {str(exc)}"


def execute_workflow(runner: InMemoryRunner, prompt: str) -> str:
    """Synchronous entry point for Gradio to run the async workflow loop."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        res = loop.run_until_complete(run_agent_workflow(runner, prompt))
        loop.close()
        return res
    except Exception as exc:
        return f"⚠️ Thread execution failed: {str(exc)}"


# ---------------------------------------------------------------------------
# Helper: Verify Connection Parameters
# ---------------------------------------------------------------------------
def verify_connection_config(conn_mode, project_id, location, api_key) -> str:
    """Check if the user supplied required cloud credentials, falling back to server environment variables."""
    if conn_mode == "Vertex AI (Google Cloud)":
        proj = (project_id or "").strip() or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        loc = (location or "").strip() or os.getenv("GOOGLE_CLOUD_LOCATION", "")
        if not proj or not loc:
            return "🔴 Please enter both GCP Project ID and Vertex AI Location."
    else:
        key = (api_key or "").strip() or os.getenv("GEMINI_API_KEY", "")
        if not key:
            return "🔴 Please enter a valid Gemini API Key."
    return ""


# ---------------------------------------------------------------------------
# Helper: Build ML Model Metrics Card (Markdown)
# ---------------------------------------------------------------------------
def build_metrics_card(raw_pred: dict) -> str:
    """Build a markdown card showing ML model info and prediction summary."""
    using_ml = raw_pred.get("using_ml_model", False)
    potability = raw_pred.get("potability", "N/A")
    safety_score = raw_pred.get("safety_score", 0)
    confidence = raw_pred.get("confidence", 0)
    n_violations = len(raw_pred.get("violations", []))
    metrics = raw_pred.get("model_metrics", {})

    # Potability badge color
    if potability == "SAFE":
        badge = "🟢 SAFE"
    elif potability == "CAUTION":
        badge = "🟡 CAUTION"
    else:
        badge = "🔴 UNSAFE"

    card = f"""
---
### ⚡ Instant Prediction Summary

| Metric | Value |
|--------|-------|
| **Potability** | {badge} |
| **Safety Score** | `{safety_score}` / 100 |
| **Confidence** | `{round(confidence * 100, 1)}%` |
| **WHO Violations** | `{n_violations}` parameter(s) |
| **Model Used** | {"🧠 Random Forest (Scikit-learn)" if using_ml else "📏 Rule-Based WHO Thresholds"} |
"""

    if metrics:
        card += f"""
---
### 📈 Trained Model Performance

| Metric | Score |
|--------|-------|
| **Accuracy** | `{round(metrics.get('accuracy', 0) * 100, 1)}%` |
| **Precision** | `{round(metrics.get('precision', 0) * 100, 1)}%` |
| **Recall** | `{round(metrics.get('recall', 0) * 100, 1)}%` |

> *Trained on [Kaggle Water Potability Dataset](https://www.kaggle.com/datasets/adityakadiwal/water-potability) · 3,276 samples · Random Forest (100 trees)*
"""
    return card


# ---------------------------------------------------------------------------
# Tab 1 Callback: Unified Water & Farm Analyzer
# ---------------------------------------------------------------------------
def run_unified_analysis(
    conn_mode, project_id, location, sa_path, api_key,
    ph, hardness, solids, chloramines, sulfate,
    conductivity, organic_carbon, trihalomethanes, turbidity,
    crop_type, season
):
    """
    Unified callback that:
    1. Runs ML potability prediction locally.
    2. Sends a combined safety + agricultural prompt to the orchestrator.
    3. Returns the metrics card + agent analysis.
    """
    conn_err = verify_connection_config(conn_mode, project_id, location, api_key)
    if conn_err:
        return conn_err

    # ML Prediction (local, instant)
    raw_pred = predict_potability(
        ph=ph, hardness=hardness, solids=solids,
        chloramines=chloramines, sulfate=sulfate,
        conductivity=conductivity, organic_carbon=organic_carbon,
        trihalomethanes=trihalomethanes, turbidity=turbidity
    )

    if raw_pred.get("status") == "error":
        return f"❌ Input Validation Error:\n{raw_pred.get('message')}"

    # Build the ML metrics card
    metrics_card = build_metrics_card(raw_pred)

    # Combined prompt for Safety + Farm assessment
    prompt = f"""
    Perform a COMBINED water quality assessment covering BOTH drinking safety AND agricultural suitability.

    === WATER SAMPLE PARAMETERS ===
    - pH: {ph if ph is not None else 'Not Provided'}
    - Hardness: {hardness if hardness is not None else 'Not Provided'}
    - Solids (TDS): {solids if solids is not None else 'Not Provided'}
    - Chloramines: {chloramines if chloramines is not None else 'Not Provided'}
    - Sulfate: {sulfate if sulfate is not None else 'Not Provided'}
    - Conductivity: {conductivity if conductivity is not None else 'Not Provided'}
    - Organic Carbon: {organic_carbon if organic_carbon is not None else 'Not Provided'}
    - Trihalomethanes: {trihalomethanes if trihalomethanes is not None else 'Not Provided'}
    - Turbidity: {turbidity if turbidity is not None else 'Not Provided'}

    === ML PREDICTION RESULTS ===
    - Potability Prediction: {raw_pred.get('potability')}
    - Safety Score: {raw_pred.get('safety_score')}/100
    - Confidence: {round(raw_pred.get('confidence', 0) * 100, 1)}%
    - Number of Violations: {len(raw_pred.get('violations', []))}

    === AGRICULTURAL CONTEXT ===
    - Crop Type: {crop_type}
    - Season: {season}

    Generate a report with these sections:
    **SECTION 1 — 🔬 Drinking Water Safety**
    1. A clear safety classification header with the potability result.
    2. Explanation of why any out-of-range parameters are dangerous.
    3. Actionable home-treatment recommendations for each violation.
    4. Vulnerable population warnings (children, elderly, pregnant).

    **SECTION 2 — 🌾 Agricultural & Irrigation Suitability**
    1. Irrigation suitability assessment based on the crop's salt tolerance.
    2. Soil health risks (salinity, pH imbalance, TDS buildup).
    3. Crop-specific management advice or water treatment recommendations.

    Use clear headings, bullet points, and emojis for readability.
    """

    runner = get_runner(project_id, location, sa_path, api_key)
    agent_result = execute_workflow(runner, prompt)

    # Combine metrics card + agent analysis
    return metrics_card + "\n\n---\n\n" + agent_result


# ---------------------------------------------------------------------------
# Tab 2 Callback: Community Alert Generator
# ---------------------------------------------------------------------------
def run_community_alert(
    conn_mode, project_id, location, sa_path, api_key,
    location_name, risk_level, violations_text, target_language
):
    """Callback for the Community Alert Generator tab."""
    conn_err = verify_connection_config(conn_mode, project_id, location, api_key)
    if conn_err:
        return conn_err

    prompt = f"""
    Generate a community water quality alert:
    - Location: {location_name}
    - Risk Level: {risk_level}
    - Issues/Violations: {violations_text}
    - Target Language: {target_language}

    Route this to the Education Agent to generate a poster/flyer content in the requested language
    (with an English translation if the target language is not English). Keep it short, high-impact,
    and include these sections:
    1. Alert headline
    2. What is the danger
    3. Who is most at risk
    4. What should people do immediately
    """
    runner = get_runner(project_id, location, sa_path, api_key)
    return execute_workflow(runner, prompt)


# ---------------------------------------------------------------------------
# Tab 3 Callback: Academy Chatbot
# ---------------------------------------------------------------------------
def run_academy_chat(
    user_message, chat_history,
    conn_mode, project_id, location, sa_path, api_key
):
    """Chatbot callback for the Water Academy tab."""
    if not user_message or not user_message.strip():
        return chat_history, ""

    conn_err = verify_connection_config(conn_mode, project_id, location, api_key)
    if conn_err:
        chat_history = chat_history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": conn_err},
        ]
        return chat_history, ""

    prompt = f"""
    The user is asking a question in the Water Academy learning chatbot.
    Their question: '{user_message}'

    Route this to the Education Agent. Respond conversationally.
    Explain in simple terms with everyday analogies,
    state health importance and standard limits/units.
    Use emojis for visual clarity. Keep the response focused and helpful.
    If the user greets you, introduce yourself as the AquaGuard Water Academy assistant.
    """
    runner = get_runner(project_id, location, sa_path, api_key)
    response = execute_workflow(runner, prompt)

    chat_history = chat_history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response},
    ]
    return chat_history, ""


# ---------------------------------------------------------------------------
# Gradio UI Construction
# ---------------------------------------------------------------------------
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');

body {
    background-color: #0f172a !important;
    font-family: 'Outfit', sans-serif !important;
    color: #f1f5f9 !important;
}
.gradio-container {
    max-width: 1280px !important;
    margin: 0 auto !important;
}
/* Force markdown prose to be bright and readable */
.prose, .prose p, .prose li, .prose ul, .prose ol,
.prose h1, .prose h2, .prose h3, .prose h4,
.prose span, .prose strong, .prose div,
.prose td, .prose th, .prose code {
    color: #f1f5f9 !important;
}
.prose h1, .prose h2, .prose h3, .prose strong {
    color: #38bdf8 !important;
}
.prose li {
    margin-bottom: 6px !important;
    color: #f1f5f9 !important;
}
.prose table {
    border-collapse: collapse !important;
    width: 100% !important;
    margin: 12px 0 !important;
}
.prose th, .prose td {
    border: 1px solid #334155 !important;
    padding: 8px 12px !important;
    text-align: left !important;
}
.prose th {
    background: #1e293b !important;
    color: #38bdf8 !important;
    font-weight: 600 !important;
}
.prose code {
    background: #1e293b !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-size: 0.95em !important;
    color: #22d3ee !important;
}
.prose blockquote {
    border-left: 3px solid #38bdf8 !important;
    padding-left: 12px !important;
    color: #94a3b8 !important;
    font-style: italic !important;
}
.prose hr {
    border-color: #334155 !important;
    margin: 20px 0 !important;
}
/* ── Chatbot bubble styling ── */
.chatbot .message-wrap .message {
    font-size: 0.95em !important;
    line-height: 1.6 !important;
}
.chatbot .bot {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #f1f5f9 !important;
}
.chatbot .bot .markdown-text,
.chatbot .bot .markdown-text p,
.chatbot .bot .markdown-text li,
.chatbot .bot .markdown-text span,
.chatbot .bot .markdown-text strong,
.chatbot .bot .markdown-text em,
.chatbot .bot .markdown-text h1,
.chatbot .bot .markdown-text h2,
.chatbot .bot .markdown-text h3,
.chatbot .bot .markdown-text h4 {
    color: #f1f5f9 !important;
}
.chatbot .bot .markdown-text strong {
    color: #38bdf8 !important;
}
.chatbot .user {
    background: linear-gradient(135deg, #0284c7, #0369a1) !important;
    color: #ffffff !important;
}
.chatbot .user .markdown-text,
.chatbot .user .markdown-text p,
.chatbot .user .markdown-text span {
    color: #ffffff !important;
}
/* Suggestion chip buttons */
.suggestion-chip {
    border: 1px solid #334155 !important;
    background: #1e293b !important;
    color: #94a3b8 !important;
    border-radius: 20px !important;
    padding: 8px 18px !important;
    font-size: 0.88em !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
}
.suggestion-chip:hover {
    background: #334155 !important;
    color: #38bdf8 !important;
    border-color: #38bdf8 !important;
    transform: translateY(-1px) !important;
}
.academy-input-row {
    border-top: 1px solid #1e293b !important;
    padding-top: 12px !important;
}
.tabitem {
    border: 1px solid #1e293b !important;
    border-top: none !important;
    padding: 24px !important;
    background: #0f172a !important;
    border-radius: 0 0 12px 12px !important;
}
.tabs {
    margin-bottom: 0px !important;
}
button.primary {
    background: linear-gradient(135deg, #38bdf8, #0284c7) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    font-size: 1.05em !important;
    padding: 12px 24px !important;
    box-shadow: 0 4px 14px 0 rgba(2, 132, 199, 0.4) !important;
    transition: all 0.2s ease !important;
}
button.primary:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px 0 rgba(2, 132, 199, 0.5) !important;
}
.header-box {
    text-align: center;
    background: linear-gradient(135deg, #1e293b, #0f172a);
    padding: 30px;
    border-radius: 12px;
    border: 1px solid #334155;
    margin-bottom: 24px;
}
.header-box h1 {
    font-size: 2.4em;
    font-weight: 800;
    background: linear-gradient(135deg, #38bdf8, #22d3ee);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
}
.header-box p {
    font-size: 1.1em;
    color: #94a3b8;
}
.connection-panel {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
}
"""


with gr.Blocks(title="AquaGuard Agent — Water Command Center") as demo:
    # ── Header ──
    gr.HTML(
        """
        <div class="header-box">
            <h1>🌊 AquaGuard Command Center</h1>
            <p>Multi-Agent Water Quality Analytics & Predictive Safety System</p>
            <div style="font-size: 0.85em; margin-top: 8px; color: #38bdf8;">
                🤖 Google ADK Multi-Agent Orchestration &nbsp;·&nbsp; 🧠 Scikit-learn Random Forest &nbsp;·&nbsp; ⚡ Gemini 2.5 Flash
            </div>
        </div>
        """
    )

    # ── Collapsible Cloud Settings ──
    # Hide if credentials exist in the server environment (for end-user production view)
    has_server_creds = bool(os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GEMINI_API_KEY"))
    with gr.Accordion("🌐 Cloud Connection Settings", open=False, visible=not has_server_creds, elem_classes="connection-panel"):
        is_vertex_default = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE").upper() == "TRUE"
        conn_mode = gr.Radio(
            choices=["Vertex AI (Google Cloud)", "Gemini API Key (Developer)"],
            value="Vertex AI (Google Cloud)" if (os.getenv("GOOGLE_CLOUD_PROJECT") or is_vertex_default) else "Gemini API Key (Developer)",
            label="Connection Mode:"
        )
        with gr.Row(visible=True) as vertex_row:
            proj_id_input = gr.Textbox(label="📁 GCP Project ID", placeholder="my-gcp-project-123", value=os.getenv("GOOGLE_CLOUD_PROJECT", ""))
            location_input = gr.Textbox(label="📍 Region", placeholder="us-central1", value=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))
            sa_key_input = gr.Textbox(label="🔑 SA Key JSON Path (Optional)", placeholder="/secrets/sa-key.json", value=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""))
        with gr.Row(visible=False) as gemini_row:
            api_key_input = gr.Textbox(label="🔑 Gemini API Key", placeholder="AIzaSy...", type="password", value=os.getenv("GEMINI_API_KEY", ""))

        def update_visibility(mode):
            if mode == "Vertex AI (Google Cloud)":
                return gr.update(visible=True), gr.update(visible=False)
            return gr.update(visible=False), gr.update(visible=True)

        conn_mode.change(update_visibility, inputs=[conn_mode], outputs=[vertex_row, gemini_row])

    # ── Main Tabs ──
    with gr.Tabs(elem_id="main-tabs"):

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # TAB 1: Unified Water & Farm Analyzer
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        with gr.TabItem("🧪 Water & Farm Analyzer"):
            with gr.Row():
                # Left: Inputs
                with gr.Column(scale=2):
                    gr.Markdown("### 🧪 Water Sample Parameters")
                    with gr.Row():
                        ph_sl = gr.Slider(0.0, 14.0, value=7.0, step=0.1, label="pH (Safe: 6.5–8.5)")
                        hardness_num = gr.Number(value=150.0, label="Hardness mg/L (<300)")
                    with gr.Row():
                        solids_num = gr.Number(value=400.0, label="TDS ppm (<500)")
                        chloramines_num = gr.Number(value=2.0, step=0.1, label="Chloramines ppm (<4)")
                    with gr.Row():
                        sulfate_num = gr.Number(value=200.0, label="Sulfate mg/L (<250)")
                        conductivity_num = gr.Number(value=350.0, label="Conductivity uS/cm (<400)")
                    with gr.Row():
                        carbon_num = gr.Number(value=1.5, step=0.1, label="Organic Carbon ppm (<2)")
                        thm_num = gr.Number(value=60.0, label="THMs ug/L (<80)")
                    with gr.Row():
                        turbidity_num = gr.Number(value=3.0, step=0.1, label="Turbidity NTU (<5)")

                    gr.Markdown("### 🌾 Agricultural Context")
                    with gr.Row():
                        crop_dd = gr.Dropdown(
                            choices=["Rice", "Wheat", "Cotton", "Corn", "Vegetables", "Sugarcane"],
                            value="Rice", label="Crop Type"
                        )
                        season_dd = gr.Dropdown(
                            choices=["Kharif / Monsoon", "Rabi / Winter", "Zaid / Summer"],
                            value="Kharif / Monsoon", label="Season"
                        )

                    analyze_btn = gr.Button("⚡ Run Water & Farm Analysis", variant="primary")

                # Right: Output
                with gr.Column(scale=3):
                    gr.Markdown("### 📊 Combined Diagnostic Report")
                    analysis_output = gr.Markdown(
                        value="*Enter your water parameters on the left and click the button to get a combined safety + agriculture assessment.*"
                    )

            analyze_btn.click(
                run_unified_analysis,
                inputs=[
                    conn_mode, proj_id_input, location_input, sa_key_input, api_key_input,
                    ph_sl, hardness_num, solids_num, chloramines_num, sulfate_num,
                    conductivity_num, carbon_num, thm_num, turbidity_num,
                    crop_dd, season_dd
                ],
                outputs=[analysis_output]
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # TAB 2: Community Alert Generator
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        with gr.TabItem("📢 Community Alert Generator"):
            with gr.Row():
                with gr.Column(scale=2):
                    gr.Markdown("### 📢 Alert Configuration")
                    loc_txt = gr.Textbox(value="Central Village", label="Community / Location Name")
                    risk_dd = gr.Dropdown(
                        choices=["LOW", "MODERATE", "HIGH", "CRITICAL"],
                        value="MODERATE", label="Assessed Risk Level"
                    )
                    violations_txt = gr.Textbox(
                        value="pH is 5.2 (Too Acidic), Turbidity is 8.5 NTU (Cloudy)",
                        label="Violations / Issues Detected",
                        lines=3
                    )
                    lang_txt = gr.Textbox(value="Spanish", label="Target Poster Language")
                    alert_btn = gr.Button("📢 Generate Community Alert", variant="primary")

                with gr.Column(scale=3):
                    gr.Markdown("### 📋 Generated Alert Poster")
                    alert_output = gr.Markdown(
                        value="*Configure the alert details on the left and click the button to generate a community flyer.*"
                    )

            alert_btn.click(
                run_community_alert,
                inputs=[
                    conn_mode, proj_id_input, location_input, sa_key_input, api_key_input,
                    loc_txt, risk_dd, violations_txt, lang_txt
                ],
                outputs=[alert_output]
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # TAB 3: Academy Chatbot
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        with gr.TabItem("📚 Water Academy"):
            academy_chatbot = gr.Chatbot(
                value=[
                    {"role": "assistant", "content": "👋 Hi! I'm your **AquaGuard Water Academy** assistant.\n\nI can help you understand water quality parameters, waterborne diseases, treatment methods, and safety standards.\n\nWhat would you like to learn about? Try one of the suggestions below, or type your own question! 💧"}
                ],
                height=480,
                show_label=False,
                layout="bubble",
                avatar_images=(None, "https://em-content.zobj.net/source/twitter/408/droplet_1f4a7.png"),
                elem_classes=["chatbot"],
                examples=[
                    {"text": "🧪 What is pH and why does it matter?"},
                    {"text": "💧 What is TDS in water?"},
                    {"text": "🦠 Tell me about Cholera"},
                    {"text": "⚠️ How does Lead get in water?"},
                    {"text": "🏥 How to prevent Typhoid?"},
                ],
            )

            # Input row
            with gr.Row(elem_classes=["academy-input-row"]):
                academy_msg = gr.Textbox(
                    placeholder="Type your question here...",
                    show_label=False,
                    scale=5,
                    lines=1,
                    container=False,
                )
                academy_send = gr.Button("Send ➤", variant="primary", scale=1, min_width=100)

            # Wire chatbot — send button and Enter key
            academy_send.click(
                run_academy_chat,
                inputs=[academy_msg, academy_chatbot, conn_mode, proj_id_input, location_input, sa_key_input, api_key_input],
                outputs=[academy_chatbot, academy_msg]
            )
            academy_msg.submit(
                run_academy_chat,
                inputs=[academy_msg, academy_chatbot, conn_mode, proj_id_input, location_input, sa_key_input, api_key_input],
                outputs=[academy_chatbot, academy_msg]
            )

            # Wire built-in example clicks
            def handle_example_click(example_msg: gr.SelectData, history, cm, pid, loc, sa, ak):
                text = example_msg.value.get("text", "") if isinstance(example_msg.value, dict) else str(example_msg.value)
                return run_academy_chat(text, history, cm, pid, loc, sa, ak)

            academy_chatbot.example_select(
                handle_example_click,
                inputs=[academy_chatbot, conn_mode, proj_id_input, location_input, sa_key_input, api_key_input],
                outputs=[academy_chatbot, academy_msg]
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # TAB 4: Dataset Explorer
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        with gr.TabItem("📊 Kaggle Dataset Explorer"):
            gr.Markdown("### 📊 Kaggle Water Potability Dataset Preprocessing")
            load_btn = gr.Button("📂 Load & Preprocess Dataset", variant="primary")
            with gr.Row():
                status_txt = gr.Textbox(label="Status", interactive=False)
                rows_num = gr.Number(label="Total Rows", interactive=False)
            with gr.Row():
                imputed_col = gr.Textbox(label="Imputed Columns", interactive=False)
                outliers_col = gr.Textbox(label="Outlier Counts Detected", interactive=False)
            stats_table = gr.JSON(label="Sample Statistics Overview")

            def load_dataset_callback():
                res = preprocess_data()
                if res.get("status") == "error":
                    return "Error", 0, "None", "None", {"Error": res.get("message")}
                imputed_str = ", ".join(res.get("imputed_columns", [])) if res.get("imputed_columns") else "None"
                outliers_str = ", ".join([f"{k}: {v}" for k, v in res.get("outlier_counts", {}).items()]) if res.get("outlier_counts") else "None"
                return (
                    "Successfully Preprocessed",
                    res.get("rows", 0),
                    imputed_str,
                    outliers_str,
                    res.get("summary_stats", {})
                )

            load_btn.click(
                load_dataset_callback,
                outputs=[status_txt, rows_num, imputed_col, outliers_col, stats_table]
            )


# Run application locally
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port, css=custom_css)
