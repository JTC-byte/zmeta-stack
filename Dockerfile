FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV ZMETA_UI_BASE_URL=http://127.0.0.1:8000
ENV ZMETA_UDP_HOST=0.0.0.0
ENV ZMETA_UDP_PORT=5005

EXPOSE 8000 5005/udp

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
