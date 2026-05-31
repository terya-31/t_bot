FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости системы (если нужны)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем pip и зависимости
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple t-tech-investments==1.49.0 && \
    pip install python-dotenv grpcio protobuf sentry-sdk python-dateutil cachetools==5.5.2 deprecation aiohttp aiohttp-socks requests

# Копируем код приложения
COPY . .

# Запуск бота
CMD ["python", "bot.py"]
