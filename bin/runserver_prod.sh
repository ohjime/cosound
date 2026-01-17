echo "Cleaning Orphaned Django Processes..."

# Added Permission to Run!

# Find matching processes (exclude the grep process itself via [] trick)
PIDS=$(ps aux | grep -E '[m]ain\.py runserver|[m]anage\.py runserver' | awk '{print $2}')

if [[ -n "$PIDS" ]]; then
  echo "$PIDS"
  # Prefer gentle kill first
  echo "$PIDS" | xargs -n1 kill 2>/dev/null
  sleep 0.5
  # Force kill any that remain
  REMAIN=$(echo "$PIDS" | xargs -n1 | while read -r p; do ps -p "$p" >/dev/null 2>&1 && echo "$p"; done)
  if [[ -n "$REMAIN" ]]; then
    echo "Force killing: $REMAIN"
    echo "$REMAIN" | xargs -n1 kill -9 2>/dev/null
  fi
else
  echo "No Django dev server processes found."
fi

echo "Cleanup complete."

echo "Starting Server..."

if [[ ! -f "pyproject.toml" ]]; then
  cd src/server
fi

uv run src/main.py proc runserver --procfile procfile.prod