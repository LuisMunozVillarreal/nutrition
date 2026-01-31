# Continues deployment

Some environment variables configuration is required:

## CircleCI

- `KUBECONFIG_DATA_BASE64`: Base64 encoded kubeconfig file.
- `GCLOUD_SERVICE_KEY`: GCP service account key for database backups.
- `DOCKER_LOGIN`: Docker Hub username.
- `DOCKER_PASSWORD`: Docker Hub password.

## GitHub

- `KUBECONFIG_DATA_BASE64`: Base64 encoded kubeconfig file.

To create the contento of the variable, execute:
```bash
base64 -w 0 ~/.kube/config > kubeconfig
```
