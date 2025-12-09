# Установка и запуск Django асинхронного сервиса

## Шаг 1: Активация виртуального окружения

В терминале выполните:

```bash
cd /Users/jane_air/Developer/WebDev/RIP/site/async-service
source env/bin/activate
```

После этого в начале строки терминала должно появиться `(env)`.

## Шаг 2: Применение миграций (опционально)

```bash
python manage.py migrate
```

Это создаст SQLite базу данных (она не используется для бизнес-логики, но требуется Django).

## Шаг 3: Запуск сервера

**Вариант 1 - Использовать скрипт (рекомендуется):**
```bash
./run.sh
```

**Вариант 2 - Использовать python из env напрямую:**
```bash
env/bin/python manage.py runserver 7070
```

**Вариант 3 - Использовать python3 (если алиас python не работает):**
```bash
python3 manage.py runserver 7070
```

Сервер запустится на `http://localhost:7070`

## Проверка работы

После запуска сервера вы должны увидеть:
```
Starting development server at http://127.0.0.1:7070/
Quit the server with CONTROL-C.
```

## Тестовый запрос

В другом терминале (или через Insomnia/Postman):
```bash
curl -X POST http://localhost:7070/api/async/process-analysis \
  -H "Content-Type: application/json" \
  -d '{"analysis_id": "test-id", "pigment_ids": [1, 2, 3]}'
```

Должен вернуть:
```json
{"status":"ok","message":"Обработка заявки test-id запущена"}
```
