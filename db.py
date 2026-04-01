import os
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator, Optional
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()


def _prefer_ipv4_from_config() -> bool:
    """Por defecto True: muchas redes no enrutan IPv6 y Supabase resuelve primero a AAAA."""
    env = os.environ.get("SUPABASE_PREFER_IPV4", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    try:
        import streamlit as st

        db = st.secrets.get("database")
        if db is not None and hasattr(db, "get"):
            v = db.get("prefer_ipv4")
            if v is not None:
                if isinstance(v, bool):
                    return v
                if isinstance(v, str):
                    s = v.strip().lower()
                    if s in ("0", "false", "no", "off", ""):
                        return False
                    if s in ("1", "true", "yes", "on"):
                        return True
                return bool(v)
    except Exception:
        pass
    return True


def _resolve_ipv4_for_host(host: str, port: int) -> Optional[str]:
    """Obtiene una IPv4 para conectar; varios métodos por si el primero falla."""
    if not host or host.startswith("["):
        return None
    # 1) Registros A
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except OSError:
        pass
    # 2) Cualquier familia y quedarse con la primera IPv4 (por si el resolver se comporta raro)
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for item in infos:
            if item[0] == socket.AF_INET:
                return item[4][0]
    except OSError:
        pass
    # 3) Resolver solo IPv4 (legacy)
    try:
        return socket.gethostbyname(host)
    except OSError:
        pass
    # 4) DNS público (1.1.1.1 / 8.8.8.8): el resolver del sistema a veces solo devuelve AAAA
    return _resolve_ipv4_via_public_dns(host)


def _resolve_ipv4_via_public_dns(host: str) -> Optional[str]:
    try:
        import dns.resolver
    except ImportError:
        return None
    if not host or host.startswith("["):
        return None
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
    resolver.timeout = 2.0
    resolver.lifetime = 6.0
    try:
        answer = resolver.resolve(host, "A")
        if answer:
            return answer[0].to_text().strip()
    except Exception:
        pass
    return None


def _prefer_ipv4_hostaddr(conn_kw: dict, enabled: bool) -> dict:
    """Fuerza TCP por IPv4 usando hostaddr; deja host para SNI/verificación SSL."""
    if not enabled:
        return conn_kw
    host = conn_kw.get("host")
    if not host or conn_kw.get("hostaddr"):
        return conn_kw
    if host.startswith("["):
        return conn_kw
    try:
        port = int(conn_kw.get("port", 5432))
        ipv4 = _resolve_ipv4_for_host(host, port)
        if ipv4:
            return {**conn_kw, "hostaddr": ipv4}
    except OSError:
        pass
    return conn_kw


def _escape_libpq_value(val: str) -> str:
    return str(val).replace("\\", "\\\\").replace("'", "\\'")


def _connect_via_libpq_keyword_string(conn_kw: dict) -> psycopg2.extensions.connection:
    """libpq a veces aplica hostaddr de forma más fiable como cadena keyword/value."""
    parts: list[str] = []
    for key in (
        "host",
        "hostaddr",
        "port",
        "dbname",
        "user",
        "password",
        "sslmode",
    ):
        if key not in conn_kw or conn_kw[key] is None:
            continue
        parts.append(f"{key}='{_escape_libpq_value(str(conn_kw[key]))}'")
    for key, val in conn_kw.items():
        if key in (
            "host",
            "hostaddr",
            "port",
            "dbname",
            "user",
            "password",
            "sslmode",
        ):
            continue
        if val is None:
            continue
        parts.append(f"{key}='{_escape_libpq_value(str(val))}'")
    conninfo = " ".join(parts)
    return psycopg2.connect(conninfo, cursor_factory=RealDictCursor)


def _parse_postgres_url(dsn: str) -> dict:
    p = urlparse(dsn)
    scheme = (p.scheme or "").lower()
    if scheme not in ("postgres", "postgresql"):
        raise RuntimeError(f"DATABASE_URL no válida (esquema: {p.scheme!r}).")
    if not p.hostname:
        raise RuntimeError("DATABASE_URL sin hostname.")
    user = unquote(p.username) if p.username else None
    password = unquote(p.password) if p.password else None
    port = p.port or 5432
    path = (p.path or "").strip("/")
    dbname = path if path else "postgres"
    q = parse_qs(p.query, keep_blank_values=True)
    sslmode = (q.get("sslmode") or ["require"])[0]
    kw: dict = {
        "host": p.hostname,
        "port": port,
        "dbname": dbname,
        "sslmode": sslmode,
    }
    if user is not None:
        kw["user"] = user
    if password is not None:
        kw["password"] = password
    return kw


def _connect_psycopg2(**kwargs) -> psycopg2.extensions.connection:
    prefer = _prefer_ipv4_from_config()
    kwargs = dict(kwargs)
    kwargs = _prefer_ipv4_hostaddr(kwargs, prefer)
    if kwargs.get("hostaddr"):
        return _connect_via_libpq_keyword_string(kwargs)
    return psycopg2.connect(cursor_factory=RealDictCursor, **kwargs)


def _try_database_from_streamlit_secrets():
    """Lee [database] o url en st.secrets (prioridad sobre .env)."""
    try:
        import streamlit as st

        db = st.secrets.get("database")
        if not db:
            return None
        url = db.get("url") or db.get("database_url")
        if url:
            return ("dsn", str(url).strip())
        host = (db.get("host") or "").strip()
        password = db.get("password")
        if password is None:
            password = ""
        else:
            password = str(password)
        if host and password:
            kw: dict = {
                "host": host,
                "port": int(db.get("port", 5432) or 5432),
                "dbname": str(db.get("name", "postgres") or "postgres").strip(),
                "user": str(db.get("user", "postgres") or "postgres").strip(),
                "password": password,
                "sslmode": str(db.get("sslmode", "require") or "require").strip(),
            }
            ha = (db.get("hostaddr") or db.get("ipv4") or "").strip()
            if ha:
                kw["hostaddr"] = ha
            return ("kwargs", kw)
    except Exception:
        pass
    return None


@dataclass(frozen=True)
class Project:
    id: str
    name: str


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    project_id: str
    group_name: Optional[str] = None


@dataclass(frozen=True)
class Edge:
    id: str
    project_id: str
    source_id: str
    target_id: str
    label: Optional[str] = None
    relation_type: Optional[str] = None


def _connect():
    """Conexión a Postgres (Supabase). Orden: secrets.toml [database] → .env / entorno.

    Por defecto se fuerza IPv4 (hostaddr) si el SO intenta IPv6 y la red no la enruta.
    """
    cfg = _try_database_from_streamlit_secrets()
    if cfg:
        kind, val = cfg
        if kind == "dsn":
            return _connect_psycopg2(**_parse_postgres_url(val))
        return _connect_psycopg2(**val)

    dsn = os.environ.get("DATABASE_URL", "").strip()
    if dsn:
        return _connect_psycopg2(**_parse_postgres_url(dsn))

    host = os.environ.get("SUPABASE_DB_HOST", "").strip()
    port = int(os.environ.get("SUPABASE_DB_PORT", "5432") or 5432)
    dbname = os.environ.get("SUPABASE_DB_NAME", "postgres").strip()
    user = os.environ.get("SUPABASE_DB_USER", "postgres").strip()
    password = os.environ.get("SUPABASE_DB_PASSWORD", "")
    sslmode = os.environ.get("SUPABASE_DB_SSLMODE", "require").strip() or "require"

    if not host or not password:
        raise RuntimeError(
            "Falta configuración de base de datos: en `.streamlit/secrets.toml` añade la "
            "sección `[database]` (host, password, etc.), o define DATABASE_URL / "
            "SUPABASE_DB_HOST + SUPABASE_DB_PASSWORD en el entorno o `.env`."
        )

    return _connect_psycopg2(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        sslmode=sslmode,
    )


@contextmanager
def db_conn() -> Generator:
    con = _connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL UNIQUE,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                  id TEXT PRIMARY KEY,
                  label TEXT NOT NULL,
                  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                  group_name TEXT,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                  source_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                  target_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                  label TEXT,
                  relation_type TEXT,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_edges_unique
                ON edges (
                  project_id,
                  source_id,
                  target_id,
                  COALESCE(label, ''),
                  COALESCE(relation_type, '')
                );
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project_id);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_project ON edges(project_id);"
            )


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def list_projects() -> list[Project]:
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM projects ORDER BY created_at DESC, name ASC"
            )
            rows = cur.fetchall()
        return [Project(id=r["id"], name=r["name"]) for r in rows]


def create_project(name: str) -> Project:
    project = Project(id=_new_id("p"), name=name.strip())
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "INSERT INTO projects(id, name) VALUES (%s, %s)",
                (project.id, project.name),
            )
    return project


def ensure_project(name: str) -> Project:
    name = name.strip()
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute("SELECT id, name FROM projects WHERE name = %s", (name,))
            row = cur.fetchone()
            if row:
                return Project(id=row["id"], name=row["name"])
    return create_project(name)


def list_nodes(project_id: str) -> list[Node]:
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT id, label, project_id, group_name
                FROM nodes
                WHERE project_id = %s
                ORDER BY created_at DESC, label ASC
                """,
                (project_id,),
            )
            rows = cur.fetchall()
        return [
            Node(
                id=r["id"],
                label=r["label"],
                project_id=r["project_id"],
                group_name=r["group_name"],
            )
            for r in rows
        ]


def create_node(project_id: str, label: str, group_name: Optional[str] = None) -> Node:
    node = Node(
        id=_new_id("n"),
        label=label.strip(),
        project_id=project_id,
        group_name=(group_name or None),
    )
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "INSERT INTO nodes(id, label, project_id, group_name) VALUES (%s, %s, %s, %s)",
                (node.id, node.label, node.project_id, node.group_name),
            )
    return node


def update_node(node_id: str, label: str, group_name: Optional[str]) -> None:
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute(
                "UPDATE nodes SET label = %s, group_name = %s WHERE id = %s",
                (label.strip(), group_name or None, node_id),
            )


def delete_node(node_id: str) -> None:
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM nodes WHERE id = %s", (node_id,))


def list_edges(project_id: str) -> list[Edge]:
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT id, project_id, source_id, target_id, label, relation_type
                FROM edges
                WHERE project_id = %s
                ORDER BY created_at DESC
                """,
                (project_id,),
            )
            rows = cur.fetchall()
        return [
            Edge(
                id=r["id"],
                project_id=r["project_id"],
                source_id=r["source_id"],
                target_id=r["target_id"],
                label=r["label"],
                relation_type=r["relation_type"],
            )
            for r in rows
        ]


def create_edge(
    project_id: str,
    source_id: str,
    target_id: str,
    label: Optional[str] = None,
    relation_type: Optional[str] = None,
) -> Edge:
    edge = Edge(
        id=_new_id("e"),
        project_id=project_id,
        source_id=source_id,
        target_id=target_id,
        label=(label.strip() if label else None),
        relation_type=(relation_type.strip() if relation_type else None),
    )
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO edges(id, project_id, source_id, target_id, label, relation_type)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    edge.id,
                    edge.project_id,
                    edge.source_id,
                    edge.target_id,
                    edge.label,
                    edge.relation_type,
                ),
            )
    return edge


def update_edge(
    edge_id: str,
    source_id: str,
    target_id: str,
    label: Optional[str],
    relation_type: Optional[str],
) -> None:
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                UPDATE edges
                SET source_id = %s, target_id = %s, label = %s, relation_type = %s
                WHERE id = %s
                """,
                (
                    source_id,
                    target_id,
                    (label.strip() if label else None),
                    (relation_type.strip() if relation_type else None),
                    edge_id,
                ),
            )


def delete_edge(edge_id: str) -> None:
    with db_conn() as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM edges WHERE id = %s", (edge_id,))
