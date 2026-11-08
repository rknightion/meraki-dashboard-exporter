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
uv python install "${PYTHON_VERSION}"
uv sync --all-extras --locked --python "${PYTHON_VERSION}"

# Fail during setup rather than leaving an agent with a partial environment.
uv run python --version
just --version

echo "Cloud task environment is ready. Run 'just check' to execute the full validation gate."
