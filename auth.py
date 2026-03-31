"""Autenticación simple para Streamlit (usuario + contraseña).

Credenciales (en este orden):
1. `.streamlit/secrets.toml` → sección [auth] con username y password
2. Variables de entorno RELATION_MAPPER_AUTH_USERNAME y RELATION_MAPPER_AUTH_PASSWORD

No guardes contraseñas en el repositorio; `secrets.toml` está en .gitignore.
"""

from __future__ import annotations

import hmac
import os
from typing import Optional, Tuple

import streamlit as st

SESSION_KEY = "relations_mapper_authenticated"


def get_expected_credentials() -> Optional[Tuple[str, str]]:
    username: Optional[str] = None
    password: Optional[str] = None
    try:
        auth = st.secrets.get("auth", {})
        username = auth.get("username")
        password = auth.get("password")
    except Exception:
        # Sin secrets.toml, Streamlit u otros errores al leer secrets
        pass
    if not username:
        username = os.environ.get("RELATION_MAPPER_AUTH_USERNAME")
    if not password:
        password = os.environ.get("RELATION_MAPPER_AUTH_PASSWORD")
    if username and password:
        return (str(username).strip(), str(password))
    return None


def _secret_equal(expected: str, provided: str) -> bool:
    a = expected.encode("utf-8")
    b = provided.encode("utf-8")
    if len(a) != len(b):
        return False
    return hmac.compare_digest(a, b)


def _credentials_match(expected: Tuple[str, str], user: str, pwd: str) -> bool:
    return _secret_equal(expected[0], user.strip()) and _secret_equal(expected[1], pwd)


def require_login(app_title: str) -> None:
    """Si no hay sesión válida, muestra el login y detiene la ejecución.

    Debes llamar a `st.set_page_config` antes que esta función.
    """
    if st.session_state.get(SESSION_KEY) is True:
        return

    expected = get_expected_credentials()

    if expected is None:
        st.error("Autenticación no configurada.")
        st.markdown(
            """
            Crea el archivo **`.streamlit/secrets.toml`** (no lo subas a git) con:

            ```toml
            [auth]
            username = "tu_usuario"
            password = "tu_contraseña"
            ```

            O define las variables de entorno **`RELATION_MAPPER_AUTH_USERNAME`** y
            **`RELATION_MAPPER_AUTH_PASSWORD`**.

            Puedes copiar `.streamlit/secrets.toml.example` como plantilla.
            """
        )
        st.stop()

    _, c, _ = st.columns([1, 2, 1])
    with c:
        st.subheader("Iniciar sesión")
        st.caption(app_title)

        with st.form("login_form", clear_on_submit=False):
            u = st.text_input("Usuario", autocomplete="username")
            p = st.text_input("Contraseña", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Entrar", type="primary", use_container_width=True)

        if submitted:
            if _credentials_match(expected, u, p):
                st.session_state[SESSION_KEY] = True
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")

    st.stop()


def logout() -> None:
    st.session_state.clear()
