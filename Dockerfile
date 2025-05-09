# Базовый образ с Python
FROM python:3.11-slim

# Рабочая директория
WORKDIR /app

# Копируем файлы
COPY . .

# Устанавливаем зависимости
RUN pip install --upgrade pip && pip install -r requirements.txt

# Устанавливаем переменные окружения, если нужно (можно убрать если .env используется)
ENV PYTHONUNBUFFERED=1

# Запуск приложения
CMD ["python", "bot.py"]
