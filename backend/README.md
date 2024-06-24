# Local development
## DB setup

1. Install `postgresql` server

2. Setup DB:

    sudo -u postgres psql < ../platform/kube/postgresql-init.sql

## Restore DB

    sudo -u postgres psql -d nutrition < db.dump


## Local environment

1. Install poetry .env plugin

    poetry self add poetry-dotenv-plugin

2. Create a local file called `.env`, with the following content:

```
POSTGRESQL_USER=<postgresql-user>
POSTGRESQL_PASSWORD=<postgresql-password>
SECRET_KEY=<django-secret-key>
```
