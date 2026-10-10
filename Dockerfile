FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BMW_PM_HOSTED=1 BMW_PM_DB_PATH=/var/data/bmw_pm.db
COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
COPY ui ./ui
COPY .streamlit/config.toml ./.streamlit/config.toml
RUN pip install --no-cache-dir ".[ai]"
EXPOSE 8501
CMD ["sh", "-c", "exec python -m streamlit run ui/app.py --server.address=0.0.0.0 --server.port=${PORT:-8501}"]
