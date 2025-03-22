# Install k3s

On a server terminal:

    ```bash
    curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--tls-san <domain> --disable=traefik" sh -
    sudo k3s kubectl config view --raw > "$KUBECONFIG"
    ```


On the client:

    ```bash
    scp -P <port> <domain>:/home/<user>/.kube/config /home/<user>/.kube/
    ```

Then edit `/home/<user>/.kube/config` and change the IP by the domain you're
using.

## Test installation

    ```bash
    kubectl get pods --all-namespaces
    ```

# Deploy platform

Check [these instructions](kube/README.md).

# Uninstall k3s

    ```bash
    /usr/local/bin/k3s-killall.sh
    ```
