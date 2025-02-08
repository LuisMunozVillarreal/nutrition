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

1. Install poetry

    ```bash
    sudo apt install python3-poetry
    ```

1. Install poetry plugins

    ```bash
    pip install --user --break-system-packages poetry-plugin-shell poetry-plugin-up poetry-plugin-dotenv
    ```
   `--breadk-system-packages` is needed to install this in Debian.

    Ideally, the following should be added to `pyproject.toml`, and packages
    would be installed from there. However, for some reason, it doesn't work.

    ```toml
    [tool.poetry.requires-plugins]
    poetry-plugin-shell = "*"
    poetry-plugin-up = "*"
    poetry-plugin-dotenv = "*"
    ```

1. Install dependencies

    ```bash
    poetry install
    ```

1. Start poetry shell

    ```bash
    poetry shell
    ```

1. Run local server

    ```bash
    ./manage.py runserver 0:8000
    ```
