#!/usr/bin/env bash
set -euo pipefail

readonly helm_version="3.19.0"
if [[ -x .venv/bin/helm && "$(.venv/bin/helm version --template '{{.Version}}')" == "v${helm_version}" ]]; then
    exit 0
fi

case "$(uname -m)" in
    x86_64)
        arch=amd64
        checksum=a7f81ce08007091b86d8bd696eb4d86b8d0f2e1b9f6c714be62f82f96a594496
        ;;
    aarch64)
        arch=arm64
        checksum=440cf7add0aee27ebc93fada965523c1dc2e0ab340d4348da2215737fc0d76ad
        ;;
    *)
        echo "Unsupported Helm architecture: $(uname -m)" >&2
        exit 1
        ;;
esac

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
archive="$scratch/helm.tar.gz"
curl -q --fail --silent --show-error --location --retry 2 \
    --proto '=https' --proto-redir '=https' \
    "https://get.helm.sh/helm-v${helm_version}-linux-${arch}.tar.gz" --output "$archive"
printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check --strict -
tar -xzf "$archive" -C "$scratch" "linux-${arch}/helm"
install -m 0755 "$scratch/linux-${arch}/helm" .venv/bin/helm
