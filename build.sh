#!/usr/bin/env bash

# Установка зависимостей
pip install -r requirements.txt

# Сборка статики
python manage.py collectstatic --no-input

# Применение миграций к базе данных
python manage.py migrate
