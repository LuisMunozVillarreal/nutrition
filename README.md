# Local development

## Backend

Check [this README](backend/README.md)

## Deploy to production

1. Install NTC

    ```bash
    poetry shell
    cd ~/repos/ntc
    pip install .
    cd -
    ```

1. Deploy to production

    ```bash
    ntc -e production cloud apply
    ```
