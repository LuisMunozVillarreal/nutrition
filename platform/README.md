# Install k3s

On a server terminal:

    curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--tls-san <domain> --disable=traefik" sh -

    sudo k3s kubectl config view --raw > "$KUBECONFIG"


On the client:

    scp -P 2222 feex.ddns.net:/home/swarf/.kube/config /home/swarf/.kube/

Then edit `/home/<user>/.kube/config` and change the IP by the domain you're 
using.

## Test installation

    kubectl get pods --all-namespaces

# Deploy platform

Check [this instructions](kube/README).

# Uninstall k3s

    /usr/local/bin/k3s-killall.sh
