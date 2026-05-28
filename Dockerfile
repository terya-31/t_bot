FROM python:3.11-slim

WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости стандартным способом
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Проверяем, что критичные библиотеки установлены
RUN python -c "from tinkoff.invest import Client; print('✅ tinkoff OK')" && \
    python -c "from aiogram import Bot; print('✅ aiogram OK')" && \
    python -c "import dotenv; print('✅ python-dotenv OK')"

# Очищаем кэш pip для уменьшения размера образа
RUN pip cache purge || true

# Устанавливаем Chrome/Chromium и зависимости для Selenium/Playwright (если нужно для парсинга)
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    xdg-utils \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Google Chrome
RUN mkdir -p /etc/apt/keyrings \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем ChromeDriver (совместимую версию с установленным Chrome)
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1) \
    && echo "Chrome version: $CHROME_VERSION" \
    && CHROME_MAJOR_VERSION=$(echo $CHROME_VERSION | cut -d. -f1) \
    && echo "Chrome major version: $CHROME_MAJOR_VERSION" \
    && (curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | grep -o '"url": "[^"]*chromedriver[^"]*linux64[^"]*"' | head -1 | cut -d'"' -f4 | wget -q -O /tmp/chromedriver.zip -i - \
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    && find /tmp -name 'chromedriver' -type f -executable -exec mv {} /usr/local/bin/chromedriver \; \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver* || echo "⚠️ ChromeDriver установка через новый API не удалась, пробуем альтернативный метод") \
    || (CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR_VERSION}" 2>/dev/null || echo "") \
    && if [ -n "$CHROMEDRIVER_VERSION" ]; then \
        wget -q "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip" -O /tmp/chromedriver.zip \
        && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
        && chmod +x /usr/local/bin/chromedriver \
        && rm /tmp/chromedriver.zip; \
    else \
        echo "⚠️ Не удалось определить версию ChromeDriver, используем webdriver-manager"; \
    fi)

# Переменные окружения для headless режима
ENV DISPLAY=:99
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver

# Копируем код приложения
COPY . .

# Директория для постоянных данных
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data && chmod 777 /app/data

# Запуск бота
CMD ["python", "bot.py"]