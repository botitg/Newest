# 🚀 ИНСТРУКЦИЯ ПО УСТАНОВКЕ

## Требования

- **Python:** 3.8 или выше
- **ОС:** Windows, macOS, Linux
- **Памяти:** 100 MB (минимум)
- **Диск:** 50 MB (для БД и зависимостей)

---

## Шаг 1: Установка Python

### Windows

1. Перейти на https://www.python.org/downloads/
2. Скачать Python 3.10 или выше
3. При установке **ОБЯЗАТЕЛЬНО** отметить:
    - ✅ "Add Python to PATH"
4. Нажать "Install Now"

### macOS

```bash
brew install python3
```

### Linux (Ubuntu/Debian)

```bash
sudo apt install python3 python3-pip python3-venv
```

---

## Шаг 2: Подготовка проекта

### Вариант A: Клонирование (если есть Git)

```bash
git clone <your-repo-url> state_game
cd state_game
```

### Вариант B: Ручная загрузка

1. Скачайте все файлы в папку `state_game`
2. Откройте терминал в этой папке

---

## Шаг 3: Создание виртуального окружения

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### macOS/Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

Вы должны увидеть `(venv)` в начале строки в терминале.

---

## Шаг 4: Установка зависимостей

```bash
pip install -r requirements.txt
```

Или расписывая:

```bash
pip install aiogram==3.4.1
pip install aiosqlite==3.0.0
pip install python-dotenv==1.0.0
```

Проверка:

```bash
pip list
```

Должны быть видны:

```
aiogram           3.4.1
aiosqlite         3.0.0
python-dotenv     1.0.0
```

---

## Шаг 5: Конфигурация

### Вариант A: Отредактировать main.py (быстро)

Откройте `main.py` и найдите строку:

```python
TOKEN = os.getenv("BOT_TOKEN", "your_token_here")
```

Замените в кавычках на ваш реальный токен.

### Вариант B: Создать .env файл (безопаснее)

Создайте файл `.env` в корне проекта:

```
BOT_TOKEN=your_real_token_here
LOG_LEVEL=INFO
```

Сохраните файл.

---

## Шаг 6: Первый запуск

```bash
python main.py
```

Если всё работает, вы должны увидеть:

```
2026-02-15 12:34:56 - main - INFO - Инициализация БД...
2026-02-15 12:34:57 - database - INFO - БД инициализирована
2026-02-15 12:34:58 - main - INFO - 🤖 Бот запущен!
2026-02-15 12:34:58 - main - INFO - Bot username: @your_bot_username
```

---

## Шаг 7: Проверка в Telegram

1. Откройте Telegram
2. Найдите вашего бота
3. Нажмите `/start`
4. Должны увидеть: 👋 Добро пожаловать!

Готово! Бот работает! 🎉

---

## 🐛 Решение проблем

### Проблема: "ModuleNotFoundError: No module named 'aiogram'"

**Причина:** Зависимости не установлены

**Решение:**

```bash
pip install -r requirements.txt
```

Или проверьте, активирован ли виртуалный окружение (должен быть `(venv)` в начале строки).

---

### Проблема: "Telegram bot not responding"

**Причина:** Неправильный токен

**Решение:**

1. Проверьте токен в main.py или .env
2. Убедитесь, что скопировали его полностью
3. Перезагрузите бот: Ctrl+C и снова `python main.py`

---

### Проблема: "sqlite3.OperationalError: database is locked"

**Причина:** Конфликт доступа к БД

**Решение:**

1. Закройте все другие подключения
2. Удалите файл `state_game_async.db`
3. Перезагрузите бот (он пересоздаст БД)

```bash
rm state_game_async.db  # Linux/macOS
del state_game_async.db # Windows
```

---

### Проблема: "Port already in use" или "Address already in use"

**Причина:** Другой процесс использует порт

**Решение:**

```bash
# Убить старый процесс (Windows)
taskkill /F /IM python.exe

# Потом запустить бот заново
python main.py
```

---

### Проблема: "ConnectionError: Too many retries"

**Причина:** Нет интернета

**Решение:**

1. Проверьте интернет-соединение
2. Проверьте, что вы не за VPN/прокси
3. Перезагрузитесь

---

### Проблема: Python не найден при запуске

**Windows:**

```bash
py main.py          # Вместо python main.py
python3 main.py     # Или так
```

**Убедитесь, что Python в PATH:**

```bash
python --version    # Должна вывести версию
```

---

## 📊 Проверка БД

Если хотите посмотреть содержимое БД:

### Вариант 1: Через Python

```bash
python
>>> import sqlite3
>>> conn = sqlite3.connect("state_game_async.db")
>>> c = conn.cursor()
>>> c.execute("SELECT * FROM users LIMIT 5")
>>> for row in c.fetchall():
...     print(row)
>>> exit()
```

### Вариант 2: Через DB Browser

1. Скачайте [DB Browser for SQLite](https://sqlitebrowser.org/)
2. Откройте файл `state_game_async.db`
3. Смотрите таблицы и данные в UI

---

## 🔍 Отладка логов

### Увеличить подробность логов

В `main.py` найдите:

```python
logging.basicConfig(
    level=logging.INFO,
    ...
)
```

Измените на:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Более подробные логи
    ...
)
```

Теперь будете видеть все операции.

### Сохранить логи в файл

Добавьте в конфигурацию логирования:

```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),  # Сохранять в файл
        logging.StreamHandler()          # Показывать в консоли
    ]
)
```

---

## 🚨 Перезагрузка БД

Если хотите начать "с чистого листа":

```bash
# 1. Остановите бот (Ctrl+C)

# 2. Удалите БД
rm state_game_async.db      # Linux/macOS
del state_game_async.db     # Windows

# 3. Запустите бот заново
python main.py

# БД пересоздастся автоматически!
```

---

## 🖥️ Варианты запуска

### Вариант 1: Обычный запуск

```bash
python main.py
```

Бот работает, пока открыта консоль.

### Вариант 2: Фоновый запуск (Linux/macOS)

```bash
nohup python main.py > bot.log 2>&1 &
```

Бот продолжит работать даже при закрытии консоли.

### Вариант 3: Systemd сервис (Linux)

Создайте файл `/etc/systemd/system/telegram-bot.service`:

```ini
[Unit]
Description=Telegram Game Bot
After=network.target

[Service]
Type=simple
User=bot
WorkingDirectory=/home/bot/state_game
ExecStart=/home/bot/state_game/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Затем:

```bash
sudo systemctl daemon-reload
sudo systemctl start telegram-bot
sudo systemctl enable telegram-bot  # Автозагрузка
```

### Вариант 4: Screen (любая ОС)

```bash
screen -S telegram-bot
python main.py

# Detach: Ctrl+A, Ctrl+D
# Вернуться: screen -r telegram-bot
```

---

## 📱 Тестирование

### Проверить основные команды

```
/start          - Должна показать меню
/help           - Справка
/profile        - Профиль
/daily          - Бонус дня (+$X)
/id             - Ваш ID
```

### Проверить режим выборов

1. Удалите БД: `rm state_game_async.db`
2. Запустите бот: `python main.py`
3. Вы должны увидеть в логах: "Выборы запущены"
4. При `/start` должны видеть меню выборов

---

## ⚡ Производительность

### Оптимизация для слабого сервера

В `main.py` измените:

```python
# Текущее (много параллельных обновлений)
application = ApplicationBuilder().token(TOKEN).concurrent_updates(4).build()

# Оптимизированное (последовательная обработка)
application = ApplicationBuilder().token(TOKEN).concurrent_updates(1).build()
```

### Оптимизация для мощного сервера

```python
# Для 1000+ одновременных пользователей
application = ApplicationBuilder().token(TOKEN).concurrent_updates(32).build()
```

---

## 📦 Обновление зависимостей

```bash
pip install --upgrade -r requirements.txt
```

Или обновить конкретный пакет:

```bash
pip install --upgrade aiogram
```

---

## 🔐 Safety Tips

1. **НИКОГДА не коммитьте токен в Git:**

    ```bash
    # Добавьте в .gitignore:
    echo ".env" >> .gitignore
    echo "*.db" >> .gitignore
    ```

2. **Используйте .env для production:**

    ```python
    from dotenv import load_dotenv
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")
    ```

3. **Ограничьте доступ к чувствительным функциям:**
    - Проверяйте ADMIN_IDS в middlewares.py
    - Логируйте все операции администраторов

---

## 📞 Получение помощи

1. Проверьте логи:

    ```bash
    less bot.log  # Linux/macOS
    type bot.log  # Windows
    ```

2. Проверьте БД:

    ```bash
    python -c "import sqlite3; conn=sqlite3.connect('state_game_async.db'); c=conn.cursor(); c.execute('SELECT count(*) FROM users'); print(c.fetchone())"
    ```

3. Убедитесь, что все файлы на месте:
    ```bash
    ls -la  # Linux/macOS
    dir /B   # Windows
    ```

---

**Happy gaming!** 🎮

_Version: 3.0_
_Last Updated: 2026-02-15_
