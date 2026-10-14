# Getting Started

Two ways to run Solo-Chat locally — Docker Compose (no local Python or Redis setup required) or manual — plus the settings modules and how to run the tests.

## Option A — Docker Compose (recommended)

**Prerequisites:** Docker Desktop

```bash
git clone https://github.com/josesholly/solo-chat.git
cd solo-chat
docker compose up --build
```

That's it. Compose starts the Django dev server and a Redis container, mounts the source directory so code changes reload without rebuilding, and binds to `http://localhost:8000`.

To create a superuser inside the running container:

```bash
docker compose exec web python manage.py createsuperuser
```

## Option B — Manual

**Prerequisites:** Python 3.11+, Redis on `localhost:6379`, [`uv`](https://github.com/astral-sh/uv)

### 1. Clone and install

```bash
git clone https://github.com/josesholly/solo-chat.git
cd solo-chat
uv sync
```

### 2. Start Redis

```bash
# macOS / Linux
redis-server

# Windows
docker run -d -p 6379:6379 redis:alpine
```

### 3. Apply migrations

```bash
python manage.py migrate
```

### 4. (Optional) Create a superuser

```bash
python manage.py createsuperuser
```

### 5. Run the server

```bash
python manage.py runserver
```

Daphne (ASGI) handles both HTTP and WebSocket. Visit `http://localhost:8000`.

## Settings environments

| Module | Used when |
|---|---|
| `config.settings.dev` | Default for `manage.py` and Docker Compose |
| `config.settings.local` | Personal overrides — copy from `dev`, gitignored |
| `config.settings.prod` | Production — all values read from environment variables |

To use local overrides, create `config/settings/local.py` (a template with commented examples is already there) and set:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.local
```

## Running tests

The suite is **pytest + pytest-django** and lives in `chat/tests/` and `games/tests/`. Redis is not required — each suite's conftest swaps the channel layer for `channels.layers.InMemoryChannelLayer` during tests.

```bash
python -m pytest                                     # everything
python -m pytest chat/tests games/tests -v           # verbose
python -m pytest games/tests/test_bot.py             # one file
python -m pytest -k "unread"                         # filter by name
```

With `uv`, prefix any of these with `uv run` (e.g. `uv run python -m pytest`).

## Linting and formatting

```bash
make lint-fix        # ruff check --fix . && ruff format .
```

## Trying password reset locally

Without `RESEND_API_KEY`, emails are printed in the server's console instead of sent. Click **Forgot password?** on the login page, enter an account's email, then copy the `/reset-password/…` link from the server output into your browser. The link works once, for one hour.

## Trying games locally

Games need two signed-in players, so open the dashboard in two browsers (or a normal and a private window) with different accounts. Both appear in each other's **Games → Players** list within a few seconds. To try it alone, use **Play vs Bot**. See [Games](games.md) for how matchmaking works.

Pytest config lives in `pyproject.toml` under `[tool.pytest.ini_options]`.
