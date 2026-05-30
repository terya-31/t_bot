# ============================================================
# БЛОК 1: ИМПОРТ НЕОБХОДИМЫХ БИБЛИОТЕК
# ============================================================

import os
import time
import datetime as dt
from dotenv import load_dotenv

import aiohttp
from aiohttp_socks import ProxyConnector
import asyncio
import uuid

# ПРАВИЛЬНЫЙ ИМПОРТ для библиотеки tinkoff-investments
# Обратите внимание: from tinkoff.invest import ... (с точкой!)
from t_tech.invest import Client, CandleInterval, OrderDirection, OrderType
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX  # песочница    from t_tech.invest.constants import INVEST_GRPC_API  # боевой




# ============================================================
# БЛОК 2: ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ИЗ ФАЙЛА .env
# ============================================================

load_dotenv()
TOKEN = os.getenv('INVEST_TOKEN')

# ========== TELEGRAM УВЕДОМЛЕНИЯ ==========
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
PROXY_URL = os.getenv('PROXY_URL')  # Например: socks5://user:pass@ip:port

# ============================================================
# БЛОК 3: НАСТРОЙКИ ТОРГОВОЙ СТРАТЕГИИ
# ============================================================

FIGI = "BBG004730RP0"      # Акции Сбера = BBG004730N88 Акции ГазПрома = BBG004730RP0
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
STOP_LOSS_PCT = 0.02       # 2% стоп-лосс
TAKE_PROFIT_PCT = 0.03     # 3% тейк-профит


# ============================================================
# БЛОК 4: ФУНКЦИИ ДЛЯ ТЕХНИЧЕСКОГО АНАЛИЗА
# ============================================================

def get_historical_candles(client, figi, days=15):
    """
    Получает исторические свечи, автоматически подбирая интервал
    """
    # Ограничиваем количество дней для 5-минутных свечей (максимум 30)
    if days <= 30:
        interval = CandleInterval.CANDLE_INTERVAL_5_MIN
        request_days = days
    else:
        interval = CandleInterval.CANDLE_INTERVAL_DAY
        request_days = days
    
    try:
        response = client.market_data.get_candles(
            figi=figi,
            from_=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=request_days),
            to=dt.datetime.now(dt.timezone.utc),
            interval=interval
        )
        
        closes = [float(candle.close.units) + float(candle.close.nano) / 1e9 
                  for candle in response.candles]
        
        if len(closes) == 0:
            print("⚠️ Нет данных за указанный период")
            return []
        
        print(f"📊 Получено {len(closes)} свечей (интервал: {'5 мин' if interval == CandleInterval.CANDLE_INTERVAL_5_MIN else 'день'})")
        return closes
        
    except Exception as e:
        print(f"⚠️ Ошибка получения свечей: {e}")
        # Если не получилось с 5-минутными, пробуем дневные
        if interval == CandleInterval.CANDLE_INTERVAL_5_MIN:
            print("🔄 Пробуем получить дневные свечи...")
            try:
                response = client.market_data.get_candles(
                    figi=figi,
                    from_=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days),
                    to=dt.datetime.now(dt.timezone.utc),
                    interval=CandleInterval.CANDLE_INTERVAL_DAY
                )
                closes = [float(candle.close.units) + float(candle.close.nano) / 1e9 
                          for candle in response.candles]
                print(f"📊 Получено {len(closes)} дневных свечей")
                return closes
            except Exception as e2:
                print(f"❌ Не удалось получить и дневные свечи: {e2}")
                return []
        return []


def calculate_rsi(prices, period=14):
    """
    Рассчитывает индекс относительной силы (RSI) на основе списка цен.
    
    Параметры:
        prices — список цен закрытия (должен быть длиннее period)
        period — период расчёта (обычно 14)
    
    Возвращает:
        значение RSI от 0 до 100
    """
    gains = []
    losses = []
    
    for i in range(1, period + 1):
        change = prices[-i] - prices[-i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


# ============================================================
# БЛОК 5: ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЗИЦИЯМИ И ЗАЯВКАМИ
# ============================================================

def get_position(client, account_id):
    """
    Проверяет, есть ли у нас открытая позиция по выбранному FIGI.
    
    Параметры:
        client — подключение к T-Invest API
        account_id — идентификатор брокерского счёта
    
    Возвращает:
        словарь с количеством лотов и средней ценой входа
        если позиции нет — {'lots': 0, 'avg_price': 0}
    """
    positions = client.operations.get_portfolio(account_id=account_id)
    
    for position in positions.positions:
        if position.figi == FIGI:
            avg_price = (float(position.average_position_price.units) + 
                         float(position.average_position_price.nano) / 1e9)
            return {
                "lots": position.quantity.units,
                "avg_price": avg_price
            }
    
    return {"lots": 0, "avg_price": 0}


def place_order(client, account_id, order_type, lots):
    """
    Выставляет рыночную заявку на покупку или продажу.
    
    Параметры:
        client — подключение к T-Invest API
        account_id — идентификатор счёта
        order_type — 'buy' или 'sell'
        lots — количество лотов
    
    Возвращает:
        объект ответа биржи
    """
    if order_type == "buy":
        direction = OrderDirection.ORDER_DIRECTION_BUY
    else:
        direction = OrderDirection.ORDER_DIRECTION_SELL
    
    order_id = str(uuid.uuid4())   #order_id = str(int(time.time() * 1000))
    
    order = client.orders.post_order(
        figi=FIGI,
        quantity=lots,
        price=None,
        direction=direction,
        account_id=account_id,
        order_type=OrderType.ORDER_TYPE_MARKET,
        order_id=order_id
    )
    return order


# ============================================================
# БЛОК 6: ОСНОВНАЯ ФУНКЦИЯ (ТОРГОВЫЙ БОТ)
# ============================================================

def main():
    print("🚀 Запуск торгового бота (ПЕСОЧНИЦА)")
    print("=" * 50)
    if not TOKEN:
        print("❌ Ошибка: токен не найден.")
        return

    # Подключаемся к API песочницы
    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        # 1. Пробуем получить список счетов в песочнице
        try:
            # ВНИМАНИЕ: В песочнице для получения счетов используется sandbox.get_sandbox_accounts()
            # а НЕ users.get_accounts()
            sandbox_accounts = client.sandbox.get_sandbox_accounts()
            accounts_list = sandbox_accounts.accounts
        except Exception as e:
            print(f"⚠️ Не удалось получить счета: {e}")
            accounts_list = []

        # 2. Если счета нет (список пуст), создаем новый
        if not accounts_list:
            print("ℹ️ В песочнице нет счетов. Создаю новый...")
            try:
                # Вызываем метод открытия счета в песочнице
                new_account_response = client.sandbox.open_sandbox_account()
                account_id = new_account_response.account_id
                print(f"✅ Создан новый счет песочницы: {account_id}")
                
                # (Опционально) Пополним счет песочницы, например, на 1 000 000 рублей
                # from t_tech.invest import MoneyValue
                # client.sandbox.sandbox_pay_in(account_id=account_id, amount=MoneyValue(currency="rub", units=1000000, nano=0))
                # print(f"💰 Счет песочницы пополнен на 1 000 000 руб.")
                
            except Exception as e:
                print(f"❌ Ошибка при создании счета: {e}")
                return
        else:
            # Если счета есть, берем первый из них
            account_id = accounts_list[0].id
            print(f"✅ Используется существующий счет песочницы: {account_id}")

            # Пополняем счёт песочницы (1 000 000 рублей)
        from t_tech.invest import MoneyValue
        try:
            client.sandbox.sandbox_pay_in(
                account_id=account_id,
                amount=MoneyValue(currency="rub", units=100000, nano=0)
            )
            print("💰 Счёт песочницы пополнен на 1 000 000 руб.")
        except Exception as e:
            print(f"⚠️ Ошибка пополнения: {e}")

        print(f"📊 Торгуем: FIGI={FIGI}")
        print("=" * 50)

        # Основной торговый цикл
        while True:
            try:
                # 1. Получаем историю цен
                candles = get_historical_candles(client, FIGI, days=25)  # используем 25 дней для надёжности
                if len(candles) < RSI_PERIOD + 1:
                    print("⏳ Недостаточно данных для расчёта RSI...")
                    time.sleep(10)
                    continue
                
                # 2. Считаем RSI и текущую цену
                rsi = calculate_rsi(candles, RSI_PERIOD)
                current_price = candles[-1]
                print(f"📈 Текущая цена: {current_price:.2f} | RSI: {rsi:.1f}")
                
                # 3. Получаем текущую позицию
                position = get_position(client, account_id)
                
                # 4. Проверяем стоп-лосс и тейк-профит
                if position["lots"] > 0:
                    entry_price = position["avg_price"]
                    
                    # Стоп-лосс
                    if current_price <= entry_price * (1 - STOP_LOSS_PCT):
                        print(f"🛑 Стоп-лосс! Цена {current_price:.2f} ≤ {entry_price * (1 - STOP_LOSS_PCT):.2f}")
                        place_order(client, account_id, "sell", position["lots"])
                        print("✅ Позиция закрыта по стоп-лоссу")
                        time.sleep(5)
                        continue
                    
                    # Тейк-профит
                    if current_price >= entry_price * (1 + TAKE_PROFIT_PCT):
                        print(f"💰 Тейк-профит! Цена {current_price:.2f} ≥ {entry_price * (1 + TAKE_PROFIT_PCT):.2f}")
                        place_order(client, account_id, "sell", position["lots"])
                        print("✅ Позиция закрыта по тейк-профиту")
                        time.sleep(5)
                        continue
                
                # 5. Сигналы на вход по RSI
                if position["lots"] == 0 and rsi < RSI_OVERSOLD:
                    print(f"🔵 Сигнал ПОКУПКИ (RSI={rsi:.1f} < {RSI_OVERSOLD})")
                    place_order(client, account_id, "buy", 10)
                    print("✅ Заявка на покупку исполнена")
                
                elif position["lots"] > 0 and rsi > RSI_OVERBOUGHT:
                    print(f"🔴 Сигнал ПРОДАЖИ (RSI={rsi:.1f} > {RSI_OVERBOUGHT})")
                    place_order(client, account_id, "sell", position["lots"])
                    print("✅ Позиция закрыта по сигналу RSI")
                
                # Ждём 30 секунд
                time.sleep(30)
                
            except KeyboardInterrupt:
                print("\n👋 Бот остановлен пользователем")
                break
            except Exception as e:
                print(f"⚠️ Ошибка: {e}")
                time.sleep(30)


# ============================================================
# БЛОК 7: ТЕЛЕГРАММ БОТ
# ============================================================

import aiohttp
import asyncio
import os
from aiohttp_socks import ProxyConnector

# ========== TELEGRAM УВЕДОМЛЕНИЯ ==========
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
PROXY_URL = os.getenv('PROXY_URL')

async def send_telegram_message(message):
    """Отправляет сообщение в Telegram через прокси"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram не настроен: нет токена или chat_id")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    print(f"📤 Отправка в Telegram: {message[:50]}...")
    
    try:
        if PROXY_URL:
            print(f"🔄 Используется прокси: {PROXY_URL.split('@')[-1] if '@' in PROXY_URL else PROXY_URL}")
            connector = ProxyConnector.from_url(PROXY_URL)
        else:
            print("🔄 Прокси не используется")
            connector = None
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    print("✅ Сообщение отправлено в Telegram")
                    return True
                else:
                    error_text = await resp.text()
                    print(f"❌ Ошибка Telegram API: {resp.status} - {error_text}")
                    return False
                    
    except asyncio.TimeoutError:
        print("❌ Таймаут подключения к Telegram")
        return False
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def send_sync_message(message):
    """Синхронная обёртка для отправки сообщений"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(send_telegram_message(message))
        loop.close()
        return result
    except Exception as e:
        print(f"❌ Ошибка при отправке сообщения: {e}")
        return False

async def _send_telegram_message(message):
    """Отправляет сообщение в Telegram через прокси"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        # Если прокси не задан — используем обычную сессию
        if PROXY_URL:
            connector = ProxyConnector.from_url(PROXY_URL)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        print(f"Ошибка отправки в Telegram: {resp.status}")
        else:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        print(f"Ошибка отправки в Telegram: {resp.status}")
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

def _send_sync_message(message):
    """Синхронная обёртка для отправки сообщений"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_telegram_message(message))
        loop.close()
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")


# ============================================================
# БЛОК 8: ЗАПУСК БОТА
# ============================================================

if __name__ == "__main__":
    main()