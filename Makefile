server:
	@cd src/server \
	 && npm install \
	 && npm run dev -- --host \
	 && npm start \

web:
	@cd src/web \
	 && npm install \
	 && npm run dev -- --host \
	 && npm start \

model:
	@cd src/model \
	 && uv sync \
	 && uv run fastapi dev \