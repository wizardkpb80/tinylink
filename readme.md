run: docker build -t my-python-app .

![local_deploy](https://github.com/user-attachments/assets/b91b9cc2-40cc-4ddc-8b27-8c174ce59f62)

полное видео в папке docs


Скриншот с БД

![image](https://github.com/user-attachments/assets/e315b009-3243-4d3f-b92e-5399922bd163)

![image](https://github.com/user-attachments/assets/b8b214b2-e932-4486-b11a-ab8fef05fd92)

![image](https://github.com/user-attachments/assets/8b630679-df60-4b2c-a021-c8305033ce54)

Генерацию ссылок отдал на откуп БД через фукцию, так же можно прилепить ещё триггер на Linkdata таблицу для сбора полной статистики 

Проект взял из лекции и доработал, по этому описываю доработки:

## 1.	User.registered_at пише дату создания
## 2.	Ручка «check-route» это работа ручек unprotected-route+protected-route

## Теперь по каталогам auth
	auth_bearer.py, auth_handler.py legacy out of project
	доработал users.py
## task:
	delete_unused_links, проверил как работает celery
	sync_usage_data – redis собирает инфу о переходах+последнее использование, а тут мы каждую минуту обновляем данные в БД, чтобы не нагружать БД 
	periodic_delete_unused_links по разным условия просроченным датам деактивирует ссылки, можно и удалять но оставил чтобы данных было поболее


# Краткое описание работы кода:

# tiny/router.py (Основной обработчик ссылок)
Этот модуль реализует API для управления короткими ссылками:

## Создание короткой ссылки (/tinylink/links/shorten):

Генерирует короткий код (или использует пользовательский alias).

Проверяет наличие дубликатов.

Сохраняет ссылку в БД и кэширует в Redis.

## Перенаправление по короткому коду (/tinylink/link/{short_code}):

Проверяет кэш в Redis, затем БД.

Увеличивает счётчик переходов (usage_count) и обновляет last_used_at.

## Удаление ссылки (/tinylink/links/{short_code}):

Удаляет ссылку из БД и Redis (только владелец).

## Обновление ссылки (/tinylink/links/{short_code}):

Позволяет изменить URL или дату истечения (только владелец).

## Статистика по ссылке (/tinylink/links/{short_code}/stats):

Возвращает количество кликов и дату последнего использования.

## Поиск ссылок по оригинальному URL (/tinylink/links/search).

## Получение списка истекших ссылок (/tinylink/links/expired).

## Деактивация неиспользуемых ссылок (/tinylink/links/deactivate_unused):

Деактивирует ссылки, не используемые N дней (только для суперпользователей).

# task/router.py (Фоновые задачи Celery)

## Удаление старых ссылок (delete_unused_links):

## Удаляет ссылки, не используемые более EXPIRATION_DAYS.

Запускается через Celery.

# task/task.py (Фоновые процессы FastAPI)

## Запуск фоновой очистки (/task/cleanup).

## Синхронизация данных из Redis в БД (sync_usage_data):

Каждые 10 секунд обновляет usage_count и last_used_at.

## Периодическое удаление неиспользуемых ссылок (periodic_delete_unused_links):

Раз в сутки помечает неиспользуемые ссылки как неактивные.

В целом, сервис оптимизирован за счёт кэширования (Redis), асинхронных операций и периодической очистки ссылок.
