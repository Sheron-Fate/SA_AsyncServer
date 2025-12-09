#!/bin/bash
# Скрипт для запуска Django сервера

cd "$(dirname "$0")"
source env/bin/activate
env/bin/python manage.py runserver 7070
