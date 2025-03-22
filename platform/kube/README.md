# Deployment

## Installation

### Pre-requisites

#### Helm 3

Make sure you have `helm` 3 installed.

#### Helm diff plugin

    ```bash
    helm plugin install https://github.com/databus23/helm-diff
    ```

#### Install Traefik Resource Definitions:

    ```bash
    kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v2.10/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml
    ```

#### Install RBAC for Traefik:

    ```bash
    kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v2.10/docs/content/reference/dynamic-configuration/kubernetes-crd-rbac.yml
    ```

#### Namespaces

    ```bash
    kubectl create namespace nutrition-staging
    kubectl create namespace nutrition-production
    ```

#### Secrets

##### Postgresql

###### Password

    ```bash
    kubectl create secret generic nutrition-postgresql --namespace nutrition-<environemnt> --from-literal=postgresql-password=<my-postgresql-password-here>
    ```

###### Init script

Edit `postgresql-init.sql` to add the password used in the previous secret.

Create the secret:

    ```bash
    kubectl create secret generic nutrition-postgresql-init-script --namespace nutrition-<environment> --from-file postgresql-init.sql
    ```

Remove the password from the file.

###### GCP credentials for DB backup

    ```bash
    kubectl create secret generic nutrition-gcp-db-backup-credentials --namespace nutrition-<environemnt> --from-file nutrition-gcp-db-backup-credentials.json
    ```

##### Django Secret Key

    ```bash
    kubectl create secret generic nutrition-django-secret-key --namespace nutrition-<environment> --from-literal=secret-key=<my-django-secret-key-here>
    ```

##### Django Secret Key

    ```bash
    kubectl create secret generic nutrition-gemini-api-key --namespace nutrition-<environment> --from-literal=gemini-api-key=<my-gemini-api-key-here>
    ```

#### Templates

Copy the templates:

    ```bash
    cp production.values.yaml-tmpl production.values.yaml
    cp staging.values.yaml-tmpl staging.values.yaml
    cp traefik.values.yaml-tmpl traefik.values.yaml
    ```

Fill the values appropriately.

#### Traefik

    ```bash
    cd platform/kube
    helmfile --debug -f helmfile.d/00-traefik.yaml apply --wait-for-jobs
    ```

#### NTC

Install NTC within the `backend` virtual environment.
Check [these instructions](../../backend/README.md) to set it up.

    ```bash
    poetry shell
    cd ~/repos/ntc
    pip install . --break-system-packages
    cd -
    ```

### Deploy to production

    ```bash
    ntc -e production cloud apply
    ```

## Uninstall

    ```bash
    helmfile --debug destroy
    ```

### Per workspace

    ```bash
    helmfile --debug destroy -n <namespace>
    ```

# Traefik dashboard

In order to view the Traefik dashboard, you need to execute the next command:

    ```bash
    kubectl -n traefik port-forward $(kubectl -n traefik get pods --selector "app.kubernetes.io/name=traefik" --output=name) 9000:9000
    ```

Then visit [localhost:9000/dashboard/](localhost:9000/dashboard/).
