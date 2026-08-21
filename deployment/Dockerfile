FROM python:3.12-slim
WORKDIR /app
COPY local-bridge/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY local-bridge/app ./app
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
