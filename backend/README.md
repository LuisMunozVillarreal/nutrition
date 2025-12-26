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
    ```

1. Install uv

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

1. Install dependencies

    ```bash
    uv sync
    ```

1. Run local server

    ```bash
    uv run ./manage.py runserver 0:8000
    ```
