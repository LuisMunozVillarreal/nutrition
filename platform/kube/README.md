# Deployment

## Installation

### Pre-requisites

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

##### Gemini API Key

    ```bash
    kubectl create secret generic nutrition-gemini-api-key --namespace nutrition-<environment> --from-literal=gemini-api-key=<my-gemini-api-key-here>
    ```

##### Garmin integration config

Garmin is disabled by default (`GARMIN_ENABLED=false`). In that state the
`nutrition-garmin-config` Secret may be absent and backend/scheduler rollout is
not blocked. To enable Garmin, create the Secret before changing
`garmin.enabled` and configure the provider endpoints/origin separately from
the application callback URL/origin in the environment values file.

The complete Secret-key inventory referenced by the workloads is:

- `client-id` (required when enabled)
- `client-secret` (required when enabled)
- `token-encryption-keys` (preferred comma-separated Fernet keyring)
- `token-encryption-key` (legacy single-key fallback)

At least one of `token-encryption-keys` or `token-encryption-key` is required
when the integration is used. Missing enabled configuration fails closed when
a Garmin operation runs; no provider request is made with incomplete config.

    ```bash
    kubectl create secret generic nutrition-garmin-config \
      --namespace nutrition-<environment> \
      --from-literal=client-id=<garmin-client-id> \
      --from-literal=client-secret=<garmin-client-secret> \
      --from-literal=token-encryption-keys=<garmin-fernet-keyring> \
      --from-literal=token-encryption-key=<legacy-garmin-fernet-key>
    ```

##### NextAuth Secret

    ```bash
    kubectl create secret generic nutrition-webapp-nextauth-secret --namespace nutrition-<environment> --from-literal=nextauth-secret=<my-nextauth-secret-here>
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

# Traefik dashboard

In order to view the Traefik dashboard, you need to execute the next command:

    ```bash
    kubectl -n traefik port-forward $(kubectl -n traefik get pods --selector "app.kubernetes.io/name=traefik" --output=name) 9000:9000
    ```

Then visit [localhost:9000/dashboard/](localhost:9000/dashboard/).
