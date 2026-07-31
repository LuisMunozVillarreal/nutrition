# Local development
## DB setup

1. Install `postgresql` server

    ```bash
    sudo apt install postgresql
    ```

2. Setup DB:

    ```bash
    sudo -u postgres psql < ../platform/kube/postgresql-init.sql
    ```

## Restore DB

    sudo -u postgres psql -d nutrition < db.dump


## Virtual environment

1. Create a local file called `.env`, with the following content:

    ```
    POSTGRESQL_USER=<postgresql-user>
    POSTGRESQL_PASSWORD=<postgresql-password>
    SECRET_KEY=<django-secret-key>
    ENVIRONMENT=development
    DEBUG=True
    ```

2. For production-like environments, also configure:

    ```
    ENVIRONMENT=production
    DEBUG=False
    SESSION_COOKIE_SECURE=True
    CSRF_COOKIE_SECURE=True
    SECURE_SSL_REDIRECT=True
    SECURE_HSTS_SECONDS=63072000
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True
    SECURE_HSTS_PRELOAD=False
    CSRF_TRUSTED_ORIGINS=<comma-separated-origins>
    ```

    Use placeholders only when documenting domain values (e.g. `${BASE_DOMAIN}`,
    `https://${BASE_DOMAIN}`), never real deployment hostnames.

3. Install uv

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

4. Install dependencies

    ```bash
    uv sync
    ```

5. Run local server

    ```bash
    uv run ./manage.py runserver 0:8000
    ```
