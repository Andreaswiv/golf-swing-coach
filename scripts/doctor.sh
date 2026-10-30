#!/usr/bin/env bash
# Checks that this machine can build and run the project. Safe to run any time; changes nothing.
# Written for macOS bash 3.2 (no associative arrays, no ${var,,}).
#
# Usage: scripts/doctor.sh
set -u

FAILS=0
WARNS=0

ok()   { printf '  [ok]   %s\n' "$1"; }
warn() { printf '  [warn] %s\n' "$1"; WARNS=$((WARNS + 1)); }
fail() { printf '  [FAIL] %s\n' "$1"; FAILS=$((FAILS + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }

echo "System"
OS="$(uname -s)"
ARCH="$(uname -m)"
printf '  %s %s\n' "$OS" "$ARCH"
if [ "$OS" = "Darwin" ]; then
  ok "macOS $(sw_vers -productVersion 2>/dev/null || echo '?')"
  if [ "$ARCH" = "arm64" ]; then
    ok "Apple Silicon (arm64)"
  else
    if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" = "1" ]; then
      fail "This shell runs under Rosetta (x86_64 emulation). Open a native arm64 terminal; emulated builds are much slower."
    else
      warn "Intel Mac detected; the project works but was targeted at Apple Silicon."
    fi
  fi
  MEM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
else
  MEM_GB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1048576 ))
fi
if [ "$MEM_GB" -ge 8 ]; then ok "${MEM_GB} GB RAM"; elif [ "$MEM_GB" -gt 0 ]; then warn "${MEM_GB} GB RAM; 8 GB+ recommended for pose estimation on long videos"; fi

FREE_GB=$(df -k . | awk 'NR==2 {print int($4/1048576)}')
if [ "$FREE_GB" -ge 10 ]; then ok "${FREE_GB} GB free disk"; else warn "${FREE_GB} GB free disk; images + videos need several GB"; fi

echo "Docker"
if have docker; then
  ok "docker $(docker --version 2>/dev/null | sed 's/Docker version //; s/,.*//')"
  if docker info >/dev/null 2>&1; then
    ok "Docker daemon is running"
    DOCKER_MEM_GB=$(( $(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0) / 1073741824 ))
    if [ "$DOCKER_MEM_GB" -ge 6 ]; then ok "Docker has ${DOCKER_MEM_GB} GB memory"; else warn "Docker has ${DOCKER_MEM_GB} GB memory; raise it to 6 GB+ in Docker Desktop settings (the .NET build and MediaPipe need it)"; fi
    DOCKER_ARCH="$(docker info --format '{{.Architecture}}' 2>/dev/null || echo ?)"
    if [ "$ARCH" = "arm64" ] && [ "$DOCKER_ARCH" != "aarch64" ] && [ "$DOCKER_ARCH" != "arm64" ]; then
      warn "Docker reports architecture '$DOCKER_ARCH' on an arm64 Mac; images may be emulated and slow"
    else
      ok "Docker architecture: $DOCKER_ARCH"
    fi
  else
    fail "Docker is installed but the daemon is not running. Start Docker Desktop."
  fi
  if docker compose version >/dev/null 2>&1; then ok "docker compose $(docker compose version --short 2>/dev/null)"; else fail "Docker Compose v2 plugin not found"; fi
else
  fail "docker not found. Install Docker Desktop for Mac (Apple Silicon)."
fi

echo "Tools for running services outside Docker (optional)"
if have dotnet; then
  ok ".NET SDK $(dotnet --version 2>/dev/null)"
  case "$(dotnet --version 2>/dev/null)" in 10.*) ;; *) warn "The backend targets net10.0; install the .NET 10 SDK to build it outside Docker" ;; esac
else
  warn ".NET SDK not found (only needed for 'dotnet test' / 'dotnet run' outside Docker; Docker builds use their own SDK image)"
fi
if have python3; then
  PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  ok "Python $PYV"
  case "$PYV" in 3.10|3.11|3.12) ;; *) warn "MediaPipe wheels are most reliable on Python 3.10-3.12 (you have $PYV). The Docker image uses 3.12." ;; esac
else
  warn "python3 not found (only needed outside Docker)"
fi
if have node; then
  ok "Node $(node --version) / npm $(npm --version 2>/dev/null)"
  NODE_MAJOR="$(node --version | sed 's/v//; s/\..*//')"
  [ "$NODE_MAJOR" -ge 20 ] || warn "Vite 7 needs Node 20.19+ or 22+"
else
  warn "node not found (only needed for 'npm run dev' outside Docker)"
fi
if have git; then ok "git $(git --version | awk '{print $3}')"; else fail "git not found"; fi
if have ollama; then ok "ollama found (used by the future coaching milestone; run it natively on macOS for GPU acceleration)"; else warn "ollama not installed (not needed until the AI coaching milestone)"; fi

echo
if [ "$FAILS" -gt 0 ]; then
  echo "$FAILS problem(s) must be fixed before 'docker compose up'. $WARNS warning(s)."
  exit 1
fi
echo "Ready. $WARNS warning(s). Next: docker compose up --build"
