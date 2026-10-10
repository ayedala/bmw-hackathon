"""Local Figma assets and IBM Plex Sans, adapted to Streamlit's native controls."""
from pathlib import Path
from base64 import b64encode
from html import escape
import streamlit as st

ASSETS = Path(__file__).with_name("assets")

@st.cache_data
def asset_url(name):
    mime = "font/ttf" if name.endswith(".ttf") else "image/svg+xml"
    return f"data:{mime};base64," + b64encode((ASSETS / name).read_bytes()).decode("ascii")

def apply_theme():
    css = Path(__file__).with_name("workbench.css").read_text(encoding="utf-8")
    css = css.replace("__FONT__", asset_url("ibm-plex-sans.ttf")).replace("__CHEVRON__", asset_url("chevron-down.svg"))
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

def brand():
    st.markdown(f'<div class="brand"><img src="{asset_url("bmw-roundel.svg")}" width="40" height="40" alt="BMW" />'
        '<div><strong>BMW Product Decision Lab</strong><small>PRODUCT MANAGEMENT / INTERNAL</small></div></div>', unsafe_allow_html=True)

def page_intro(title, subtitle):
    st.markdown(f'<div class="page-intro"><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>', unsafe_allow_html=True)

def badge(status):
    labels = {"needs_review": "Under review", "draft": "Draft", "approve": "Approved", "reject": "Rejected", "challenge": "Challenged", "defer": "Deferred", "edit": "Edited"}
    return f'<span class="status-badge status-{escape(status, quote=True)}">{escape(labels.get(status, status.replace("_", " ").title()))}</span>'

def workflow(mode_label):
    steps = ["Sources", "Normalize", "Findings", "Requirements", "Score", "PM review", "Audit"]
    arrow = f'<img src="{asset_url("arrow-right.svg")}" width="16" height="16" alt="" />'
    st.markdown('<div class="workflow"><div class="workflow-steps">' + arrow.join(f'<span>{label}</span>' for label in steps)
        + f'</div><p>{escape(mode_label)}. Sources and scope remain traceable; a PM records the decision and rationale.</p></div>', unsafe_allow_html=True)

def source_row(source, url):
    name = source.get("original_name_or_url", source["source_id"])
    display_name = Path(name).name if source.get("local_or_web") == "local" else name
    icon = "file-spreadsheet.svg" if any(display_name.lower().endswith(ext) for ext in (".csv", ".xlsx", ".xls")) else "file-text.svg"
    link = f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">Open original source ↗</a>' if url else '<span>Imported source</span>'
    st.markdown(f'<div class="source-row"><img src="{asset_url(icon)}" width="20" height="20" alt="" />'
        f'<div><strong>{escape(display_name)}</strong><small>{link}</small></div></div>', unsafe_allow_html=True)
