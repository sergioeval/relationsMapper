import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Optional
from uuid import uuid4


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


def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    return con


@contextmanager
def db_conn(db_path: str) -> Iterable[sqlite3.Connection]:
    con = _connect(db_path)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(db_path: str) -> None:
    with db_conn(db_path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        # If this is an existing DB, nodes/edges may not have project_id yet.
        # We'll create new tables with project_id and migrate.
        nodes_cols = {r["name"] for r in con.execute("PRAGMA table_info(nodes);").fetchall()} if _table_exists(con, "nodes") else set()
        edges_cols = {r["name"] for r in con.execute("PRAGMA table_info(edges);").fetchall()} if _table_exists(con, "edges") else set()

        needs_migration = ("project_id" not in nodes_cols) or ("project_id" not in edges_cols)

        if needs_migration:
            default_project = ensure_project(db_path, "Default")
            _migrate_to_projects(con, default_project.id)

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS nodes (
              id TEXT PRIMARY KEY,
              label TEXT NOT NULL,
              project_id TEXT NOT NULL,
              group_name TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS edges (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              target_id TEXT NOT NULL,
              label TEXT,
              relation_type TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
              FOREIGN KEY(source_id) REFERENCES nodes(id) ON DELETE CASCADE,
              FOREIGN KEY(target_id) REFERENCES nodes(id) ON DELETE CASCADE
            );
            """
        )
        con.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_edges_unique
            ON edges(project_id, source_id, target_id, IFNULL(label, ''), IFNULL(relation_type, ''));
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_edges_project ON edges(project_id);")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def list_projects(db_path: str) -> list[Project]:
    with db_conn(db_path) as con:
        rows = con.execute("SELECT id, name FROM projects ORDER BY created_at DESC, name ASC").fetchall()
        return [Project(id=r["id"], name=r["name"]) for r in rows]


def create_project(db_path: str, name: str) -> Project:
    project = Project(id=_new_id("p"), name=name.strip())
    with db_conn(db_path) as con:
        con.execute("INSERT INTO projects(id, name) VALUES (?, ?)", (project.id, project.name))
    return project


def ensure_project(db_path: str, name: str) -> Project:
    name = name.strip()
    with db_conn(db_path) as con:
        row = con.execute("SELECT id, name FROM projects WHERE name = ?", (name,)).fetchone()
        if row:
            return Project(id=row["id"], name=row["name"])
    return create_project(db_path, name)


def _migrate_to_projects(con: sqlite3.Connection, default_project_id: str) -> None:
    # Migrate nodes
    if _table_exists(con, "nodes"):
        cols = {r["name"] for r in con.execute("PRAGMA table_info(nodes);").fetchall()}
        if "project_id" not in cols:
            con.execute("ALTER TABLE nodes RENAME TO nodes_old;")
            con.execute(
                """
                CREATE TABLE nodes (
                  id TEXT PRIMARY KEY,
                  label TEXT NOT NULL,
                  project_id TEXT NOT NULL,
                  group_name TEXT,
                  created_at TEXT NOT NULL DEFAULT (datetime('now')),
                  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                """
            )
            con.execute(
                """
                INSERT INTO nodes(id, label, project_id, group_name, created_at)
                SELECT id, label, ?, group_name, created_at
                FROM nodes_old;
                """,
                (default_project_id,),
            )
            con.execute("DROP TABLE nodes_old;")

    # Migrate edges
    if _table_exists(con, "edges"):
        cols = {r["name"] for r in con.execute("PRAGMA table_info(edges);").fetchall()}
        if "project_id" not in cols:
            con.execute("ALTER TABLE edges RENAME TO edges_old;")
            con.execute(
                """
                CREATE TABLE edges (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  source_id TEXT NOT NULL,
                  target_id TEXT NOT NULL,
                  label TEXT,
                  relation_type TEXT,
                  created_at TEXT NOT NULL DEFAULT (datetime('now')),
                  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                  FOREIGN KEY(source_id) REFERENCES nodes(id) ON DELETE CASCADE,
                  FOREIGN KEY(target_id) REFERENCES nodes(id) ON DELETE CASCADE
                );
                """
            )
            con.execute(
                """
                INSERT INTO edges(id, project_id, source_id, target_id, label, relation_type, created_at)
                SELECT id, ?, source_id, target_id, label, relation_type, created_at
                FROM edges_old;
                """,
                (default_project_id,),
            )
            con.execute("DROP TABLE edges_old;")

def list_nodes(db_path: str, project_id: str) -> list[Node]:
    with db_conn(db_path) as con:
        rows = con.execute(
            """
            SELECT id, label, project_id, group_name
            FROM nodes
            WHERE project_id = ?
            ORDER BY created_at DESC, label ASC
            """,
            (project_id,),
        ).fetchall()
        return [
            Node(id=r["id"], label=r["label"], project_id=r["project_id"], group_name=r["group_name"])
            for r in rows
        ]


def create_node(db_path: str, project_id: str, label: str, group_name: Optional[str] = None) -> Node:
    node = Node(
        id=_new_id("n"),
        label=label.strip(),
        project_id=project_id,
        group_name=(group_name or None),
    )
    with db_conn(db_path) as con:
        con.execute(
            "INSERT INTO nodes(id, label, project_id, group_name) VALUES (?, ?, ?, ?)",
            (node.id, node.label, node.project_id, node.group_name),
        )
    return node


def update_node(db_path: str, node_id: str, label: str, group_name: Optional[str]) -> None:
    with db_conn(db_path) as con:
        con.execute(
            "UPDATE nodes SET label = ?, group_name = ? WHERE id = ?",
            (label.strip(), group_name or None, node_id),
        )


def delete_node(db_path: str, node_id: str) -> None:
    with db_conn(db_path) as con:
        con.execute("DELETE FROM nodes WHERE id = ?", (node_id,))


def list_edges(db_path: str, project_id: str) -> list[Edge]:
    with db_conn(db_path) as con:
        rows = con.execute(
            """
            SELECT id, project_id, source_id, target_id, label, relation_type
            FROM edges
            WHERE project_id = ?
            ORDER BY created_at DESC
            """,
            (project_id,),
        ).fetchall()
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
    db_path: str,
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
    with db_conn(db_path) as con:
        con.execute(
            """
            INSERT INTO edges(id, project_id, source_id, target_id, label, relation_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (edge.id, edge.project_id, edge.source_id, edge.target_id, edge.label, edge.relation_type),
        )
    return edge


def update_edge(
    db_path: str,
    edge_id: str,
    source_id: str,
    target_id: str,
    label: Optional[str],
    relation_type: Optional[str],
) -> None:
    with db_conn(db_path) as con:
        con.execute(
            """
            UPDATE edges
            SET source_id = ?, target_id = ?, label = ?, relation_type = ?
            WHERE id = ?
            """,
            (
                source_id,
                target_id,
                (label.strip() if label else None),
                (relation_type.strip() if relation_type else None),
                edge_id,
            ),
        )


def delete_edge(db_path: str, edge_id: str) -> None:
    with db_conn(db_path) as con:
        con.execute("DELETE FROM edges WHERE id = ?", (edge_id,))

