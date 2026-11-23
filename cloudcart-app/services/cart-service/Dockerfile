
FROM python:3.12-slim

WORKDIR /app

COPY services/common/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY services/cart-service/main.py .

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
