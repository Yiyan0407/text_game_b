import streamlit as st

from config.settings import get_settings


def render_login_gate() -> None:
    settings = get_settings()

    st.title("🔒 AI 跑团")
    st.caption("请输入访问密码")

    with st.form("login_form"):
        password = st.text_input("密码", type="password", placeholder="请输入密码")
        submitted = st.form_submit_button("进入", type="primary", use_container_width=True)

    if submitted:
        if password == settings.app_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("密码错误")
