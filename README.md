# Relation Mapper (Streamlit + Supabase / Postgres)

Proyecto para crear **mapas visuales** de **nodos** y **relaciones**, guardando la información en **PostgreSQL** (conexión directa, p. ej. **Supabase**). La app exige **inicio de sesión**; solo quien tenga usuario y contraseña configurados puede usarla.

## Requisitos

- Python 3.10+ recomendado
- Proyecto Supabase (o cualquier Postgres) y contraseña del usuario `postgres`

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` incluye `psycopg2-binary` (driver compatible con `import psycopg2`).

## Configuración: `.streamlit/secrets.toml`

Es el lugar **principal** para credenciales (auth + base de datos). No lo subas a git.

```bash
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edita `secrets.toml` y completa:

- **`[auth]`**: usuario y contraseña para **entrar a la app**.
- **`[database]`**: `host`, `port`, `name`, `user`, `password`, `sslmode` (Supabase), o una sola clave **`url`** con la connection string de Postgres.

Al arrancar, `db.py` crea las tablas si no existen (`projects`, `nodes`, `edges`).

**Supabase e IPv6:** el host **directo** `db.*.supabase.co` suele ser **solo IPv6**. Si falla la conexión, usa el pooler del panel (**IPv4**). **Transaction pooler:** puerto **6543**, usuario **`postgres.TUREF`** (ej. `postgres.ivotmktmqvkblmrocbhm`), host tipo `aws-1-us-east-2.pooler.supabase.com` (según región y lo que muestre el panel). Valores de ejemplo en `.streamlit/secrets.toml.example`.

Opcional: `prefer_ipv4 = false` en `[database]` o `SUPABASE_PREFER_IPV4=0` si quieres el comportamiento por defecto del resolver (p. ej. IPv6 funcional).

### Alternativa sin secrets (CI / Docker)

Variables de entorno: `DATABASE_URL` o `SUPABASE_DB_HOST` + `SUPABASE_DB_PASSWORD`, etc. También puedes usar un archivo **`.env`** (ver `.env.example`) como respaldo; **si existen ambos**, prevalece lo definido en **`secrets.toml`** para la base de datos.

**Login de la app por entorno:** `RELATION_MAPPER_AUTH_USERNAME` y `RELATION_MAPPER_AUTH_PASSWORD`.

En la app: **Menú → Cerrar sesión**.

## Ejecutar

```bash
streamlit run app.py
```

## Estructura

- `app.py`: UI Streamlit + grafo
- `auth.py`: login
- `db.py`: Postgres + CRUD
- `.streamlit/secrets.toml.example`: plantilla **auth + database**
- `.env.example`: opcional, variables para entorno / desarrollo
