import streamlit as st

from config.logging_setup import setup_logging
from ui.debug_page import render_debug_page

st.set_page_config(page_title="Debug 日志", page_icon="🐛", layout="wide")

setup_logging()
render_debug_page()
