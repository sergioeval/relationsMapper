import os

import psycopg2
import streamlit as st
from pyvis.network import Network

import auth as app_auth
import db as graphdb


APP_TITLE = "Relation Mapper (Streamlit + Postgres)"


def render_network(nodes: list[graphdb.Node], edges: list[graphdb.Edge]) -> str:
    net = Network(height="650px", width="100%", bgcolor="#0b0f17", font_color="#e5e7eb", directed=True)
    net.barnes_hut(gravity=-20000, central_gravity=0.3, spring_length=150, spring_strength=0.01, damping=0.2)

    group_palette = [
        "#60a5fa",  # blue
        "#34d399",  # green
        "#fbbf24",  # amber
        "#f472b6",  # pink
        "#a78bfa",  # violet
        "#fb7185",  # rose
        "#22c55e",  # emerald
        "#38bdf8",  # sky
    ]

    group_to_color: dict[str, str] = {}
    for n in nodes:
        group = n.group_name or "default"
        if group not in group_to_color:
            group_to_color[group] = group_palette[len(group_to_color) % len(group_palette)]
        net.add_node(
            n.id,
            label=n.label,
            title=f"<b>{n.label}</b><br/>{n.id}<br/>grupo: {n.group_name or '-'}",
            color=group_to_color[group],
        )

    for e in edges:
        edge_label = e.label or e.relation_type or ""
        title_parts = [f"{e.source_id} → {e.target_id}"]
        if e.relation_type:
            title_parts.append(f"tipo: {e.relation_type}")
        if e.label:
            title_parts.append(f"label: {e.label}")
        net.add_edge(
            e.source_id,
            e.target_id,
            label=edge_label,
            title="<br/>".join(title_parts),
            arrows="to",
            color="#94a3b8",
        )

    net.set_options(
        """
        var options = {
          "interaction": { "hover": true, "navigationButtons": true, "keyboard": true },
          "physics": { "enabled": true, "stabilization": { "iterations": 150 } },
          "nodes": { "shape": "dot", "size": 16, "font": { "size": 14 } },
          "edges": { "smooth": { "type": "dynamic" }, "font": { "size": 12, "align": "top" } }
        }
        """
    )

    return net.generate_html()


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    app_auth.require_login(APP_TITLE)

    st.title(APP_TITLE)
    st.caption("Crea nodos/relaciones, persiste en Postgres (Supabase), y visualiza el grafo.")
    st.markdown(
        """
        <style>
          /* Make button labels stay on one line */
          div.stButton > button {
            white-space: nowrap;
          }
          /* Keep selectbox text on a single line too */
          div[data-baseweb="select"] * {
            white-space: nowrap;
          }
          /* Ensure the selected value doesn't wrap */
          div[data-baseweb="select"] [data-testid="stSelectbox"] {
            white-space: nowrap;
          }
          div[data-baseweb="select"] > div {
            min-width: 0;
          }
          /* If the label/value is too long, truncate with ellipsis */
          div[data-baseweb="select"] span,
          div[data-baseweb="select"] div {
            overflow: hidden;
            text-overflow: ellipsis;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    try:
        graphdb.init_db()
    except psycopg2.OperationalError as e:
        err = str(e)
        st.error("No se pudo conectar a la base de datos.")
        if "Network is unreachable" in err or "2600:" in err:
            st.markdown(
                """
                El host **directo** `db.*.supabase.co` suele ser **solo IPv6**. Muchas redes no
                enrutan IPv6 y por eso falla la conexión.

                **Qué hacer:** en el panel de Supabase, **Settings → Database → Connect**,
                elige **Session pooler** (o **Transaction pooler**) y copia **host** (algo como
                `aws-0-REGION.pooler.supabase.com`), **puerto** y **usuario** que te muestre.
                Actualiza la sección `[database]` en `.streamlit/secrets.toml`.

                Más detalle en `.streamlit/secrets.toml.example`.
                """
            )
        st.code(err, language="text")
        st.stop()

    projects = graphdb.list_projects()
    if not projects:
        graphdb.ensure_project("Default")
        projects = graphdb.list_projects()
    project_by_id = {p.id: p for p in projects}

    if "selected_project_id" not in st.session_state or st.session_state["selected_project_id"] not in project_by_id:
        st.session_state["selected_project_id"] = projects[0].id
    selected_project_id = st.session_state["selected_project_id"]

    nodes = graphdb.list_nodes(selected_project_id)
    edges = graphdb.list_edges(selected_project_id)
    node_by_id = {n.id: n for n in nodes}

    @st.dialog("Proyecto")
    def project_dialog() -> None:
        st.subheader("Seleccionar proyecto")
        current_projects = graphdb.list_projects()
        if not current_projects:
            graphdb.ensure_project("Default")
            current_projects = graphdb.list_projects()
        by_id = {p.id: p for p in current_projects}

        pid = st.selectbox(
            "Proyecto",
            options=[p.id for p in current_projects],
            format_func=lambda x: by_id[x].name,
            index=[p.id for p in current_projects].index(st.session_state.get("selected_project_id", current_projects[0].id)),
            key="dlg_project_select",
        )
        if st.button("Usar este proyecto", type="primary", use_container_width=True, key="dlg_btn_use_project"):
            st.session_state["selected_project_id"] = pid
            st.rerun()

        st.divider()
        st.subheader("Crear nuevo proyecto")
        new_project_name = st.text_input("Nombre", key="dlg_new_project_name")
        if st.button("Crear proyecto", use_container_width=True, key="dlg_btn_create_project"):
            if not new_project_name.strip():
                st.error("El nombre no puede estar vacío.")
            else:
                try:
                    p = graphdb.create_project(new_project_name)
                    st.session_state["selected_project_id"] = p.id
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo crear el proyecto: {e}")

    @st.dialog("Nuevo nodo")
    def create_node_dialog() -> None:
        new_label = st.text_input("Label", key="dlg_new_node_label")
        new_group = st.text_input("Grupo (opcional)", key="dlg_new_node_group")
        if st.button("Crear", type="primary", use_container_width=True, key="dlg_btn_create_node"):
            if not new_label.strip():
                st.error("El label no puede estar vacío.")
            else:
                graphdb.create_node(selected_project_id, new_label, new_group)
                st.rerun()

    @st.dialog("Nueva relación")
    def create_edge_dialog() -> None:
        if len(nodes) < 2:
            st.info("Necesitas al menos 2 nodos para crear una relación.")
            return
        src = st.selectbox(
            "Origen",
            options=[n.id for n in nodes],
            format_func=lambda nid: f"{node_by_id[nid].label} ({nid})",
            key="dlg_new_edge_src",
        )
        dst = st.selectbox(
            "Destino",
            options=[n.id for n in nodes],
            format_func=lambda nid: f"{node_by_id[nid].label} ({nid})",
            key="dlg_new_edge_dst",
        )
        rel_type = st.text_input("Tipo (opcional)", key="dlg_new_edge_type")
        rel_label = st.text_input("Label (opcional)", key="dlg_new_edge_label")
        if st.button("Crear", type="primary", use_container_width=True, key="dlg_btn_create_edge"):
            if src == dst:
                st.error("Origen y destino no pueden ser el mismo nodo.")
            else:
                try:
                    graphdb.create_edge(selected_project_id, src, dst, rel_label, rel_type)
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo crear la relación: {e}")

    @st.dialog("Administrar (editar / borrar)")
    def manage_dialog() -> None:
        tab_nodes, tab_edges = st.tabs(["Nodos", "Relaciones"])

        with tab_nodes:
            if not nodes:
                st.info("Aún no hay nodos.")
            else:
                node_id = st.selectbox(
                    "Nodo",
                    options=[n.id for n in nodes],
                    format_func=lambda nid: f"{node_by_id[nid].label} ({nid})",
                    key="dlg_edit_node_id",
                )
                # Keys por nodo: si no, Streamlit mantiene el texto del registro anterior.
                n_sel = node_by_id[node_id]
                edit_label = st.text_input(
                    "Nuevo label",
                    value=n_sel.label,
                    key=f"dlg_edit_node_label_{node_id}",
                )
                edit_group = st.text_input(
                    "Nuevo grupo (opcional)",
                    value=n_sel.group_name or "",
                    key=f"dlg_edit_node_group_{node_id}",
                )

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Guardar cambios", type="primary", use_container_width=True, key="dlg_btn_save_node"):
                        if not edit_label.strip():
                            st.error("El label no puede estar vacío.")
                        else:
                            graphdb.update_node(node_id, edit_label, edit_group)
                            st.rerun()
                with c2:
                    if st.button("Borrar nodo", use_container_width=True, key="dlg_btn_delete_node"):
                        graphdb.delete_node(node_id)
                        st.rerun()

        with tab_edges:
            if not edges:
                st.info("Aún no hay relaciones.")
            else:
                edge_by_id = {e.id: e for e in edges}
                edge_id = st.selectbox(
                    "Relación",
                    options=[e.id for e in edges],
                    format_func=lambda eid: f"{edge_by_id[eid].source_id} → {edge_by_id[eid].target_id} ({eid})",
                    key="dlg_edit_edge_id",
                )
                edge = edge_by_id[edge_id]
                if len(nodes) < 2:
                    st.info("Necesitas al menos 2 nodos para editar relaciones.")
                    return
                node_ids = [n.id for n in nodes]
                # Keys por relación: origen/destino y textos reflejan el registro elegido.
                src2 = st.selectbox(
                    "Origen",
                    options=node_ids,
                    index=node_ids.index(edge.source_id) if edge.source_id in node_by_id else 0,
                    format_func=lambda nid: f"{node_by_id[nid].label} ({nid})",
                    key=f"dlg_edit_edge_src_{edge_id}",
                )
                dst2 = st.selectbox(
                    "Destino",
                    options=node_ids,
                    index=node_ids.index(edge.target_id) if edge.target_id in node_by_id else 0,
                    format_func=lambda nid: f"{node_by_id[nid].label} ({nid})",
                    key=f"dlg_edit_edge_dst_{edge_id}",
                )
                rel_type2 = st.text_input(
                    "Tipo (opcional)",
                    value=edge.relation_type or "",
                    key=f"dlg_edit_edge_type_{edge_id}",
                )
                rel_label2 = st.text_input(
                    "Label (opcional)",
                    value=edge.label or "",
                    key=f"dlg_edit_edge_label_{edge_id}",
                )

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Guardar cambios", type="primary", use_container_width=True, key="dlg_btn_save_edge"):
                        if src2 == dst2:
                            st.error("Origen y destino no pueden ser el mismo nodo.")
                        else:
                            graphdb.update_edge(edge_id, src2, dst2, rel_label2, rel_type2)
                            st.rerun()
                with c2:
                    if st.button("Borrar relación", use_container_width=True, key="dlg_btn_delete_edge"):
                        graphdb.delete_edge(edge_id)
                        st.rerun()

    header_left, header_right = st.columns([0.82, 0.18], gap="small", vertical_alignment="center")
    with header_left:
        st.markdown(f"##### Proyecto: {project_by_id[selected_project_id].name}")
    with header_right:
        with st.popover("Menú", use_container_width=True):
            m1, m2 = st.columns(2, gap="small")
            with m1:
                if st.button("Nuevo nodo", type="primary", use_container_width=True, key="menu_btn_new_node"):
                    create_node_dialog()
            with m2:
                if st.button("Nueva relación", type="primary", use_container_width=True, key="menu_btn_new_edge"):
                    create_edge_dialog()
            m3, m4 = st.columns(2, gap="small")
            with m3:
                if st.button("Administrar", use_container_width=True, key="menu_btn_manage"):
                    manage_dialog()
            with m4:
                if st.button("Proyecto", use_container_width=True, key="menu_btn_project"):
                    project_dialog()
            if st.button("Refrescar", use_container_width=True, key="menu_btn_refresh"):
                st.rerun()
            if st.button("Cerrar sesión", use_container_width=True, key="menu_btn_logout"):
                app_auth.logout()
                st.rerun()

    if not nodes:
        st.info("Crea nodos para ver el mapa.")
    else:
        html = render_network(nodes, edges)
        st.components.v1.html(html, height=820, scrolling=True)

        st.subheader("Datos (debug)")
        with st.expander("Ver nodos/relaciones en tablas", expanded=False):
            st.write([n.__dict__ for n in nodes])
            st.write([e.__dict__ for e in edges])


if __name__ == "__main__":
    main()

