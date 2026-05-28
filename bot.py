import os
import time
from dotenv import load_dotenv
from tinkoff.invest import Client

# Загружаем токен из файла .env
load_dotenv()
TOKEN = os.getenv('INVEST_TOKEN')

# Параметры стратегии
FIGI = "BBG004730N88"      # Акции Сбера (можно заменить)
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
STOP_LOSS_PCT = 0.02       # 2% стоп-лосс
TAKE_PROFIT_PCT = 0.03     # 3% тейк-профит

def get_historical_candles(client, figi, days=30):
    """Получает исторические свечи для расчета RSI"""
    from tinkoff.invest import CandleInterval
    import datetime as dt
    
    # Запрашиваем свечи за последние days дней
    response = client.market_data.get_candles(
        figi=figi,
        from_=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days),
        to=dt.datetime.now(dt.timezone.utc),
        interval=CandleInterval.CANDLE_INTERVAL_5_MIN
    )
    
    # Извлекаем цены закрытия
    closes = [float(candle.close.units) + float(candle.close.nano) / 1e9 
              for candle in response.candles]
    return closes

def calculate_rsi(prices, period=14):
    """Вычисляет RSI на основе списка цен закрытия"""
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

def get_position(client, account_id):
    """Возвращает текущую позицию по FIGI"""
    positions = client.operations.get_portfolio(account_id=account_id)
    for position in positions.positions:
        if position.figi == FIGI:
            return {
                "lots": position.quantity.units,
                "avg_price": float(position.average_position_price.units) 
                             + float(position.average_position_price.nano) / 1e9
            }
    return {"lots": 0, "avg_price": 0}

def place_order(client, account_id, order_type, lots):
    """Выставляет рыночную заявку на покупку или продажу"""
    from tinkoff.invest import OrderDirection, OrderType
    
    direction = (OrderDirection.ORDER_DIRECTION_BUY if order_type == "buy" 
                 else OrderDirection.ORDER_DIRECTION_SELL)
    
    order = client.orders.post_order(
        figi=FIGI,
        quantity=lots,
        price=None,  # None = рыночная заявка
        direction=direction,
        account_id=account_id,
        order_type=OrderType.ORDER_TYPE_MARKET,
        order_id=str(int(time.time() * 1000))
    )
    return order

def main():
    print("🚀 Запуск торгового бота")
    print("=" * 50)
    
    # Проверяем токен
    if not TOKEN:
        print("❌ Ошибка: токен не найден. Создайте файл .env с INVEST_TOKEN=ваш_токен")
        return
    
    with Client(TOKEN) as client:
        # Получаем счета
        accounts = client.users.get_accounts()
        if not accounts.accounts:
            print("❌ Нет доступных счетов")
            return
        
        account_id = accounts.accounts[0].id
        print(f"✅ Используется счёт: {account_id}")
        print(f"📊 Торгуем: FIGI={FIGI}")
        print("=" * 50)
        
        while True:
            try:
                # 1. Получаем историю цен
                candles = get_historical_candles(client, FIGI)
                if len(candles) < RSI_PERIOD + 1:
                    print("⏳ Недостаточно данных для расчёта RSI...")
                    time.sleep(10)
                    continue
                
                # 2. Считаем RSI
                rsi = calculate_rsi(candles, RSI_PERIOD)
                current_price = candles[-1]
                print(f"📈 Текущая цена: {current_price:.2f} | RSI: {rsi:.1f}")
                
                # 3. Получаем текущую позицию
                position = get_position(client, account_id)
                
                # 4. Проверяем условия позиции (стоп-лосс / тейк-профит)
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
                    order = place_order(client, account_id, "buy", 1)
                    print(f"✅ Заявка исполнена. Номер: {order.order_id}")
                
                elif position["lots"] > 0 and rsi > RSI_OVERBOUGHT:
                    print(f"🔴 Сигнал ПРОДАЖИ (RSI={rsi:.1f} > {RSI_OVERBOUGHT})")
                    order = place_order(client, account_id, "sell", position["lots"])
                    print(f"✅ Позиция закрыта. Номер: {order.order_id}")
                
                # Ждём 30 секунд до следующей проверки
                time.sleep(30)
                
            except Exception as e:
                print(f"⚠️ Ошибка: {e}")
                time.sleep(30)

if __name__ == "__main__":
    main()