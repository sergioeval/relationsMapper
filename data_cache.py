"""Caché de lecturas a BD con las APIs nativas de Streamlit.

- ``@st.cache_resource``: ``init_db`` una vez por proceso worker.
- ``@st.cache_data``: listados; se invalida con ``revision`` + ``scope`` por sesión
  (evita mezclar datos entre usuarios en el mismo servidor).
"""

from __future__ import annotations

import secrets

import streamlit as st

import db as graphdb


def ensure_session_cache_scope() -> str:
    """Identificador único por sesión del navegador."""
    if "cache_scope_id" not in st.session_state:
        st.session_state["cache_scope_id"] = secrets.token_hex(16)
    return st.session_state["cache_scope_id"]


def get_data_revision() -> int:
    return int(st.session_state.get("data_cache_revision", 0))


def bump_data_cache() -> None:
    """Llamar tras cualquier escritura en BD o al pulsar Refrescar."""
    st.session_state["data_cache_revision"] = get_data_revision() + 1


@st.cache_resource
def ensure_database_schema() -> bool:
    graphdb.init_db()
    return True


@st.cache_data(show_spinner=False)
def load_projects(scope: str, revision: int) -> tuple[graphdb.Project, ...]:
    return tuple(graphdb.list_projects())


@st.cache_data(show_spinner=False)
def load_nodes(scope: str, revision: int, project_id: str) -> tuple[graphdb.Node, ...]:
    return tuple(graphdb.list_nodes(project_id))


@st.cache_data(show_spinner=False)
def load_edges(scope: str, revision: int, project_id: str) -> tuple[graphdb.Edge, ...]:
    return tuple(graphdb.list_edges(project_id))
