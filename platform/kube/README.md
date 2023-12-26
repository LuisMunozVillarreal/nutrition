# Deployment

## Installation

### Pre-requisites

#### Helm 3

Make sure you have `helm` 3 installed.

#### Helm diff plugin

    helm plugin install https://github.com/databus23/helm-diff

#### Install Traefik Resource Definitions:

    kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v2.10/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml

#### Install RBAC for Traefik:

    kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v2.10/docs/content/reference/dynamic-configuration/kubernetes-crd-rbac.yml

#### Namespaces

    kubectl create namespace nutrition-staging

    kubectl create namespace nutrition-production

#### Secrets

##### Postgresql

    kubectl create secret generic nutrition-postgresql --namespace nutrition-<environemnt> --from-literal=postgresql-password=<my-postgresql-password-here>

##### Django Secret Key

    kubectl create secret generic nutrition-django-secret-key --namespace nutrition-<environment> --from-literal=secret-key=<my-django-secret-key-here>

### Platform

The following instructions will install all releases.
`helmfile -f <path-to-file>` can be used to install individual releases. Check
`helmfile.d` directory to find all the release files.

All releases:

    cd platform/kube

    helmfile --debug apply --wait-for-jobs

Individual release:

    helmfile --debug -f helmfile.d/00-traefik.yaml apply --wait-for-jobs

## Upgrade

The following instructions will install all releases.
`helmfile -f <path-to-file>` can be used to install individual releases. Check
`helmfile.d` directory to find all the release files.

    helmfile --debug apply --wait-for-jobs

## Uninstall

    helmfile --debug destroy


# Traefik dashboard

In order to view the Traefik dashboard, you need to execute the next command:

    kubectl -n traefik port-forward $(kubectl -n traefik get pods --selector "app.kubernetes.io/name=traefik" --output=name) 9000:9000

Then visit [localhost:9000/dashboard/](localhost:9000/dashboard/).
