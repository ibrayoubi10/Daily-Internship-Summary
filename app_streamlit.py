import json
from pathlib import Path
import base64
import streamlit.components.v1 as components

import streamlit as st

from app.config import (
    APP_TITLE,
    RECORDINGS_DIR,
    OUTPUTS_DIR,
    WHISPER_MODEL_SIZE,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    OLLAMA_URL,
    OLLAMA_MODEL_NAME,
    DEFAULT_LANGUAGE,
)

from app.services.transcriber import TranscriberService
from app.services.summarizer import SummarizerService
from app.services.storage import StorageService

# -----------------------------
# Utils to downlaod files 
# -----------------------------
def auto_download_file(file_bytes: bytes, filename: str, mime: str):
    b64 = base64.b64encode(file_bytes).decode()
    html = f"""
    <html>
    <body>
        <a id="download_link" href="data:{mime};base64,{b64}" download="{filename}"></a>
        <script>
            document.getElementById('download_link').click();
        </script>
    </body>
    </html>
    """
    components.html(html, height=0)

# -----------------------------
# Init page
# -----------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title("Daily Internship Summary")
st.caption("your daily summary of internship tasks and learnings")


# -----------------------------
# Session state
# -----------------------------
def init_state():
    defaults = {
        "audio_path": None,
        "transcription": "",
        "structured_data": {},
        "summary_text": "",
        "initialized": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# -----------------------------
# Services init
# -----------------------------
@st.cache_resource
def get_transcriber():
    return TranscriberService(
        WHISPER_MODEL_SIZE,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
    )


@st.cache_resource
def get_summarizer():
    return SummarizerService(OLLAMA_URL, OLLAMA_MODEL_NAME)


@st.cache_resource
def get_storage():
    return StorageService(RECORDINGS_DIR, OUTPUTS_DIR)


transcriber = get_transcriber()
summarizer = get_summarizer()
storage = get_storage()


# -----------------------------
# Helpers
# -----------------------------
def fill_default_structure(data: dict) -> dict:
    data = data or {}
    data.setdefault("summary", "")
    data.setdefault("action_items", [])
    data.setdefault("completed_items", [])
    data.setdefault("important_points", [])
    data.setdefault("blockers", [])
    data.setdefault("keywords", [])
    data.setdefault("priority", "medium")
    return data


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.header("Settings")
    st.write(f"Whisper model: `{WHISPER_MODEL_SIZE}`")
    st.write(f"Ollama model: `{OLLAMA_MODEL_NAME}`")
    st.write(f"Language: `{DEFAULT_LANGUAGE}`")

    if st.button("Reset current session", use_container_width=True):
        st.session_state.audio_path = None
        st.session_state.transcription = ""
        st.session_state.structured_data = {}
        st.session_state.summary_text = ""
        st.rerun()


# -----------------------------
# Audio input
# -----------------------------
st.subheader("1. Record audio")

audio_file = st.audio_input("Record a voice note", sample_rate=16000)

if audio_file is not None:
    ts = storage.timestamp()
    paths = storage.build_session_paths(ts)

    audio_bytes = audio_file.getbuffer()
    paths["audio"].write_bytes(audio_bytes)

    st.session_state.audio_path = str(paths["audio"])

    st.success(f"Audio saved: {paths['audio'].name}")
    st.audio(audio_file)

    # auto download in browser
    auto_download_file(
        bytes(audio_bytes),
        paths["audio"].name,
        "audio/wav"
    )


# -----------------------------
# Actions
# -----------------------------
st.subheader("2. Process")

col1, col2 = st.columns(2)

with col1:
    if st.button(
        "Transcribe audio",
        disabled=st.session_state.audio_path is None,
        use_container_width=True,
    ):
        try:
            with st.spinner("Transcribing..."):
                text = transcriber.transcribe(
                    st.session_state.audio_path,
                    language=DEFAULT_LANGUAGE,
                )

            st.session_state.transcription = text

            current_audio_path = Path(st.session_state.audio_path)
            ts = current_audio_path.stem.replace("recording_", "")
            paths = storage.build_session_paths(ts)
            storage.save_text(paths["transcription"], text)

            st.success("Transcription completed.")
        except Exception as e:
            st.error(f"Transcription error: {e}")

with col2:
    if st.button(
        "Generate structured summary",
        disabled=not bool(st.session_state.transcription.strip()),
        use_container_width=True,
    ):
        try:
            with st.spinner("Generating structured summary..."):
                structured = summarizer.summarize_structured(
                    st.session_state.transcription
                )

            structured = fill_default_structure(structured)

            st.session_state.structured_data = structured
            st.session_state.summary_text = structured.get("summary", "")

            current_audio_path = Path(st.session_state.audio_path)
            ts = current_audio_path.stem.replace("recording_", "")
            paths = storage.build_session_paths(ts)

            storage.save_text(paths["summary"], st.session_state.summary_text)
            storage.save_json(paths["structured"], structured)

            st.success("Structured summary completed.")
        except Exception as e:
            st.error(f"Summary error: {e}")

# -----------------------------
# Display area
# -----------------------------
st.subheader("3. Results")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Transcription", "Summary", "Tasks", "Important", "JSON"]
)

with tab1:
    st.text_area(
        "Transcription",
        value=st.session_state.transcription,
        height=300,
    )

with tab2:
    priority = st.session_state.structured_data.get("priority", "medium")
    summary_value = st.session_state.summary_text

    st.text_area(
        "Summary",
        value=summary_value,
        height=220,
    )
    st.markdown(f"**Priority:** {priority}")

with tab3:
    tasks = st.session_state.structured_data.get("action_items", [])
    completed = st.session_state.structured_data.get("completed_items", [])

    st.markdown("### Action items")
    if tasks:
        for item in tasks:
            st.checkbox(item, value=False)
    else:
        st.info("No action items found.")

    st.markdown("### Completed items")
    if completed:
        for item in completed:
            st.write(f"- {item}")
    else:
        st.info("No completed items found.")

with tab4:
    important_points = st.session_state.structured_data.get("important_points", [])
    blockers = st.session_state.structured_data.get("blockers", [])
    keywords = st.session_state.structured_data.get("keywords", [])

    st.markdown("### Important points")
    if important_points:
        for item in important_points:
            st.write(f"- {item}")
    else:
        st.info("No important points found.")

    st.markdown("### Blockers")
    if blockers:
        for item in blockers:
            st.write(f"- {item}")
    else:
        st.info("No blockers found.")

    st.markdown("### Keywords")
    if keywords:
        st.write(", ".join(keywords))
    else:
        st.info("No keywords found.")

with tab5:
    st.json(st.session_state.structured_data or {})