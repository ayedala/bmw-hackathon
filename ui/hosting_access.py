from __future__ import annotations

import time
from pathlib import Path

import streamlit as st

from bmw_pm.hosting import (hosted_settings, install_snapshot, password_matches, session_fingerprint)


def require_hosted_access() -> Path:
    try:
        settings = hosted_settings()
    except ValueError:
        st.error("Hosting access is not configured. The service owner must configure separate team and setup passwords of at least 20 characters.")
        st.stop()
    marker = session_fingerprint(settings.app_password)
    authenticated = st.session_state.get("hosting_login")
    if not authenticated or authenticated[0] != marker or time.time() > authenticated[1]:
        st.subheader("Team sign-in")
        blocked_until = st.session_state.get("login_blocked_until", 0)
        with st.form("hosted_login"):
            password = st.text_input("Team password", type="password")
            submitted = st.form_submit_button("Sign in")
        if submitted:
            if time.time() < blocked_until:
                st.error("Too many attempts. Try again in one minute.")
            elif password_matches(password, settings.app_password):
                st.session_state["hosting_login"] = (marker, time.time() + 1800)
                st.session_state["login_failures"] = 0
                st.rerun()
            else:
                failures = st.session_state.get("login_failures", 0) + 1
                st.session_state["login_failures"] = failures
                if failures >= 5:
                    st.session_state["login_blocked_until"] = time.time() + 60
                    st.session_state["login_failures"] = 0
                st.error("Incorrect password.")
        st.stop()
    if st.sidebar.button("Sign out"):
        st.session_state.clear()
        st.rerun()
    target = Path(settings.database_path)
    if not target.is_file():
        st.subheader("Initial database setup")
        st.write("Upload the approved private database snapshot. Existing data cannot be replaced through this screen.")
        if not settings.bootstrap_sha256:
            st.info("The service owner must first set BMW_PM_BOOTSTRAP_SHA256 from the prepared snapshot manifest.")
            st.stop()
        with st.form("database_setup"):
            upload = st.file_uploader("Canonical database snapshot", type=["db"])
            admin_password = st.text_input("Setup password", type="password")
            restore = st.form_submit_button("Install approved snapshot")
        if restore and upload is not None:
            try:
                with st.spinner("Validating and installing evidence"):
                    install_snapshot(upload.getvalue(), settings, admin_password)
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error(str(exc))
        st.stop()
    return target
