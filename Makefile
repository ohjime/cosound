server:
	@cd src/server \
	 && npm install \
	 && npm run dev -- --host

web:
	@cd src/web \
	 && npm install \
	 && npm run dev -- --host

model:
	@cd src/model \
	 && uv sync \
	 && uv run fastapi dev \