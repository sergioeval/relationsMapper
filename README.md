# Relation Mapper (Streamlit + SQLite)

Proyecto para crear **mapas visuales** de **nodos** y **relaciones**, guardando toda la información en una base de datos **SQLite**. La app exige **inicio de sesión**; solo quien tenga usuario y contraseña configurados puede usarla.

## Requisitos

- Python 3.10+ recomendado

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Autenticación

1. Copia la plantilla y crea tu archivo de secretos (no lo subas a git):

   ```bash
   mkdir -p .streamlit
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

2. Edita `.streamlit/secrets.toml` y pon tu **usuario** y **contraseña** en la sección `[auth]`.

**Alternativa (servidor / Docker):** variables de entorno `RELATION_MAPPER_AUTH_USERNAME` y `RELATION_MAPPER_AUTH_PASSWORD`.

En la app, **Menú → Cerrar sesión** termina la sesión.

## Ejecutar

```bash
streamlit run app.py
```

La base de datos local se usa en `graph.sqlite` (se crea al usar la app; está ignorada por git).

## Estructura

- `app.py`: UI Streamlit + visualización del grafo
- `auth.py`: login con `secrets` o variables de entorno
- `db.py`: esquema SQLite + CRUD de nodos/relaciones/proyectos
- `.streamlit/secrets.toml.example`: plantilla de credenciales
