#!/usr/bin/env bash
# Configure a Codex Cloud or Claude Code cloud container for development and validation.
# Use this command in either product's environment setup-script field:
#   bash scripts/cloud-environment-setup.sh

set -euo pipefail

readonly JUST_VERSION="1.58.0"
readonly PYTHON_VERSION="3.14.7"
readonly UV_VERSION="0.12.9"
readonly USER_BIN="${HOME}/.local/bin"

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

setup_python() {
    uv python install "${PYTHON_VERSION}"
    uv sync --all-extras --locked --python "${PYTHON_VERSION}" "$@"
}

install_cursor_helm() (
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
)

if [[ "${1:-}" == --cursor ]]; then
    export UV_PROJECT_ENVIRONMENT=.venv
    setup_python --compile-bytecode
    install_cursor_helm
    exit 0
fi

mkdir -p "${USER_BIN}"
export PATH="${USER_BIN}:${PATH}"

# Setup and agent commands do not share a shell. Persist the user-local bin
# directory so tools bootstrapped here remain available to either cloud agent.
path_line='export PATH="$HOME/.local/bin:$PATH"'
touch "${HOME}/.bashrc"
if ! grep -Fqx "${path_line}" "${HOME}/.bashrc"; then
    printf '\n%s\n' "${path_line}" >> "${HOME}/.bashrc"
fi

installed_uv_version=""
if command -v uv >/dev/null 2>&1; then
    installed_uv_version="$(uv --version | awk '{print $2}')"
fi

if [[ "${installed_uv_version}" != "${UV_VERSION}" ]]; then
    echo "Installing uv ${UV_VERSION}..."
    curl --proto '=https' --tlsv1.2 -LsSf \
        "https://astral.sh/uv/${UV_VERSION}/install.sh" | env UV_INSTALL_DIR="${USER_BIN}" sh
fi

installed_just_version=""
if command -v just >/dev/null 2>&1; then
    installed_just_version="$(just --version | awk '{print $2}')"
fi

if [[ "${installed_just_version}" != "${JUST_VERSION}" ]]; then
    echo "Installing just ${JUST_VERSION}..."
    curl --proto '=https' --tlsv1.2 -LsSf https://just.systems/install.sh | \
        bash -s -- --tag "${JUST_VERSION}" --to "${USER_BIN}"
fi

echo "Installing Python ${PYTHON_VERSION} and locked development dependencies..."
setup_python

# Fail during setup rather than leaving an agent with a partial environment.
uv run python --version
just --version

echo "Cloud task environment is ready. Run 'just check' to execute the full validation gate."
