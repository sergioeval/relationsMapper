# Relation Mapper (Streamlit + SQLite)

Proyecto para crear **mapas visuales** de **nodos** y **relaciones**, guardando toda la información en una base de datos **SQLite**.

## Requisitos

- Python 3.10+ recomendado

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecutar

```bash
streamlit run app.py
```

Por defecto la base de datos se crea/usa en `graph.sqlite` (en el directorio del proyecto).

Opcionalmente puedes definir la ruta con una variable de entorno:

```bash
RELATION_MAPPER_DB=/ruta/a/mi.sqlite streamlit run app.py
```

## Estructura

- `app.py`: UI Streamlit + visualización del grafo
- `db.py`: esquema SQLite + CRUD de nodos/relaciones
- `graph.sqlite`: se genera al correr la app (si no existe)

