player:
ifeq ($(run),clean)
	@echo "Cleaning Player Build..."
	@rm -rf build/player.app/
	@rm -rf src/player/build/
	@rm -rf src/player/src/build/
	@rm -rf src/player/media/
	@echo "Deleting Python Cache..."
	@cd src/player \
		&& find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "Player cleaned!"
else ifdef build
	@echo "Building Player for $(build)..."
	@cd src/player \
		&& uv sync
	@rm -rf src/player/media/
	@if [ "$(build)" = "macos" ]; then \
			cd src/player && uv run flet build macos --arch arm64 x64; \
			rm -rf build/player.app; \
			mkdir -p build; \
			cp -R src/player/build/macos/player.app build/; \
			rm -rf src/player/build; \
			rm -rf src/player/src/build; \
			fi
	@echo "Build completed in ./build/"
else ifdef run
	@echo "Running command in Player Environment..."
	@cd src/player \
		&& $(run)
else
	@reset
	@cd src/player \
		&& uv sync \
		&& uv pip install pip -q
	@echo "Starting Player..."
	@cd src/player \
		&& uv run flet run src/main.py
endif

server:
ifeq ($(run),clean)
	@echo "Cleaning Server..."
	@echo "Deleting Python Cache..."
	@cd src/server/src \
		&& find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "Deleting Django Migrations..."
	@cd src/server/src \
		&& find . -type f -path "*/migrations/*.py" ! -name "__init__.py" ! -name "0001*.py" -exec rm -f {} +
	@echo "Deleting Databases..."
	@-dropdb --force cosounds > /dev/null 2>&1
	@echo "Deleting Node Modules..."
	@cd src/server/vite \
		&& find . -type d -name "node_modules" -exec rm -rf {} +
	@echo "Deleting Vite Builds..."
	@cd src/server/vite \
		&& find . -type d -name "static" -exec rm -rf {} +	
else ifdef run
	@echo "Running command in Server Environment..."
	@cd src/server \
		&& $(run)
else
	@reset
	@chmod +x bin/clean_honcho.sh
	@echo "Cleaning Orphaned Django Processes..."
	@./bin/clean_honcho.sh
	@echo "Installing dependencies..."
	@cd src/server \
		&& uv sync
	@echo "Setting Up Database..."
	@-createdb cosounds
	@echo "Building Vite Assets..."
	@cd src/server/vite \
		&& npm install \
		&& npm run build
	@echo "Making Migrations..."
	@cd src/server \
		&& uv run src/main.py makemigrations \
		&& uv run src/main.py migrate
	@echo "Running tests..."
	@echo "All tests passed!"
	@echo "Server is ready!"
	@echo "Starting Server..."
	@cd src/server \
		&& uv run src/main.py proc runserver --procfile procfile.dev
endif

superuser:
	@echo "Creating superuser for Central Backend..."
	@cd src/server \
		&& uv sync
	@cd src/server \
		&& uv run src/main.py createsuperuser