"""Shared-password gate.

This dashboard holds internal division tracking, demographic preferences and
ground-campaign field notes, and it spends an OpenAI key on every question. It
must not be walk-up accessible once it leaves localhost.

Fails closed: with no APP_PASSWORD configured the app refuses to render rather
than silently serving the data to anyone who finds the URL.
"""

import hmac

import streamlit as st

SESSION_KEY = "_authenticated"


def _configured_password():
    try:
        return st.secrets.get("APP_PASSWORD")
    except Exception:
        return None


def require_password():
    """Render the lock screen and stop the script unless the viewer is in."""
    if st.session_state.get(SESSION_KEY):
        return

    expected = _configured_password()

    if not expected:
        st.error(
            "**APP_PASSWORD is not set.** This app serves internal campaign data, so it "
            "refuses to start without one. Add a line to `.streamlit/secrets.toml` "
            "(locally) or to the host's secrets manager (when deployed):\n\n"
            "```toml\nAPP_PASSWORD = \"choose-a-long-passphrase\"\n```"
        )
        st.stop()

    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.markdown("### People's Mandate AI")
        st.caption("Internal campaign tool. Enter the team password to continue.")
        entered = st.text_input("Password", type="password", label_visibility="collapsed")

        if entered:
            # compare_digest keeps the check constant-time
            if hmac.compare_digest(entered, str(expected)):
                st.session_state[SESSION_KEY] = True
                st.rerun()
            else:
                st.error("Incorrect password.")

    st.stop()
