FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python -m recoverpilot.data.generate --rows 8000 && python -m recoverpilot.ml.train

EXPOSE 8000 8501

CMD ["uvicorn", "recoverpilot.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
