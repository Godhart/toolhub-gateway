# ToolHub Nginx Docker 0.3.0 — HTTPS + OAuth

В Compose: Nginx, Certbot, Keycloak, PostgreSQL и внутренний сервис проверки Bearer-токенов. На хосте нужны Docker Engine, Compose **2.24+** и shell. Nginx защищает все маршруты ToolHub; metadata и страница входа Keycloak остаются публичными. Сам ToolHub изменять не требуется.

## Быстрый запуск

```bash
cp .env.example .env
```

Укажите реальные значения:

```dotenv
DOMAIN=tools.your-domain.net
EMAIL=you@your-domain.net
TOOLHUB_UPSTREAM=toolhub-router:3000
TOOLHUB_CONTAINER=actual-router-container
TOOLHUB_NETWORK=toolhub-edge
MCP_PATH=/mcp
TOOLHUB_USERNAME=toolhub-user
OAUTH_REDIRECT_URI=https://chatgpt.com/connector_platform_oauth_redirect
NGINX_IMAGE=nginx:stable-alpine
CERTBOT_IMAGE=certbot/certbot:latest
```

MCP_PATH — действующий endpoint вашей версии ToolHub, например `/mcp` для Streamable HTTP или `/sse` для SSE. Путь не создаётся этим комплектом. Resource identifier будет `https://DOMAIN/MCP_PATH` с точным совпадением пути и завершающего слеша. TOOLHUB_UPSTREAM — имя/alias и **внутренний HTTP-порт** роутера. 3000 здесь только пример.

TOOLHUB_CONTAINER — реальное имя существующего контейнера ToolHub. Скрипт подключает его к общей сети с alias из TOOLHUB_UPSTREAM. Если нужная сеть/alias уже настроены, оставьте TOOLHUB_CONTAINER пустым. Уже подключённому контейнеру alias скрипт не меняет: используйте его действующее DNS-имя.

В `.env` допустимы доверенные POSIX строки NAME=value. Файл читается shell: не помещайте туда команды. Пароли вручную задавать не требуется.

```bash
sh deploy.sh
```

Скрипт собирает образы, генерирует постоянные секреты и realm, запускает PostgreSQL/Keycloak, дожидается discovery, выпускает сертификат через HTTP bootstrap и включает защищённый HTTPS. Затем запускает автоматическое продление. Повторный deploy сохраняет сертификат, пароли и БД.

Откройте локальный `config/credentials.txt`: там пользователь/пароль для входа, Client ID/Secret для ChatGPT и административные данные Keycloak. Этот файл и config/secrets.json имеют права 0600; каталог config — 0700. Не удаляйте config при обновлении. Первичный пароль случайный, действующих паролей по умолчанию нет.

## Подключение в ChatGPT

1. Откройте ChatGPT в браузере, Plugins → «+» → Add custom MCP server.
2. Server URL: `https://tools.your-domain.net/mcp` (или ваш MCP_PATH).
3. Authentication: OAuth. Укажите **предварительно зарегистрированный** клиент:
   - Client ID: `chatgpt-toolhub`;
   - Client Secret: из `config/credentials.txt`.
4. Сверьте callback/Redirect URI на странице настройки ChatGPT с OAUTH_REDIRECT_URI. Он должен совпадать **буквально**. Если ChatGPT показывает другой адрес, замените OAUTH_REDIRECT_URI в .env и выполните `sh update-oauth-client.sh` после запуска сервера.
5. Сохраните/установите плагин, выберите его в чате и выполните вход. Откроется Keycloak: введите логин/пароль из credentials.txt. Пароль пользователя вводится на странице Keycloak, а Client Secret — в настройке подключения.

Доступные публичные metadata:

```text
https://tools.your-domain.net/.well-known/oauth-protected-resource
https://tools.your-domain.net/auth/realms/toolhub/.well-known/openid-configuration
```

Authorization endpoint: `/auth/realms/toolhub/protocol/openid-connect/auth`.
Token endpoint: `/auth/realms/toolhub/protocol/openid-connect/token`.
Issuer: `https://tools.your-domain.net/auth/realms/toolhub`.
Scope: `mcp:tools` (также добавлен клиенту как default scope).

Выбран статический клиент, поскольку текущая официальная документация Keycloak отмечает несовместимость его CIMD с форматом metadata ChatGPT. CIMD/DCR не являются обязательными для заранее зарегистрированного клиента. Keycloak требует PKCE S256 и выдаёт refresh-токены; password/client-credentials/implicit grants для этого клиента выключены.

Используется **resource-indicators**, экспериментальная функция Keycloak, для проверки OAuth `resource` и привязки aud к реальному MCP URL. Версия Keycloak закреплена на 26.7.4; при её обновлении повторно проверьте полный OAuth flow. Без подходящего resource/audience токен доступ не получает.

## Что защищено

Все запросы, попадающие в ToolHub, включая tools/list, tools/call, POST endpoint SSE и его UI, проходят auth_request. Без Bearer-токена возвращается 401 с WWW-Authenticate и адресом metadata; при недостаточной роли/scope — 403. Обычная браузерная сессия/cookie не заменяет Bearer-токен для ToolHub, поэтому UI через этот внешний прокси также требует токен. При необходимости администрируйте ToolHub через его отдельный локальный доступ.

Проверяются RS256-подпись через доверенный JWKS Keycloak, iss, aud, exp, iat, sub, typ=Bearer, azp=chatgpt-toolhub, scope=mcp:tools и realm role toolhub-access. Подписанные токены другого клиента, ID tokens и токены другого ресурса отклоняются. При недоступности валидатора или JWKS доступ закрыт (Nginx может вернуть 5xx).

Первому пользователю назначена роль toolhub-access; саморегистрация выключена. Все пользователи с этой ролью получают один и тот же набор инструментов ToolHub. Разделения workspace/прав по отдельным тулам эта версия не добавляет.

JWT access token живёт 5 минут. Отключение пользователя/отзыв сессии препятствует дальнейшему входу и refresh, но уже выданный подписанный токен может работать до expiry (плюс 10 секунд допуск на часы). Проверка по JWKS не является онлайн-introspection. Это не влияет на саму возможность отозвать refresh-сессию.

Внешние порты опубликованы только для Nginx. Keycloak admin/master realm не проксируются публично; управление — через контейнерные CLI helpers. Убедитесь, что прежний публичный порт ToolHub закрыт, иначе по нему можно обойти OAuth этого прокси.

## Управление пользователем и callback

Посмотреть пользователя:

```bash
sh keycloak-admin.sh get users -r toolhub -q username=toolhub-user
```

Изменить пароль:

```bash
sh keycloak-admin.sh set-password -r toolhub --username toolhub-user --new-password 'YOUR_NEW_PASSWORD'
```

Команда передаёт пароль аргументом: при необходимости очистите историю shell. credentials.txt хранит первоначальные bootstrap-данные и после такого изменения не отражает новый пароль; генератор не сбрасывает пароль существующего пользователя. Изменять роль/отключать пользователя можно через kcadm с его ID:

```bash
sh keycloak-admin.sh update users/USER_ID -r toolhub -s enabled=false
```

Callback меняется так:

```bash
# Измените OAUTH_REDIRECT_URI в .env на точный адрес из ChatGPT.
sh update-oauth-client.sh
```

Keycloak импортирует realm только при первом старте; повторный deploy **не меняет** уже существующую конфигурацию realm. Изменения callback выполняются helper-скриптом. Изменения DOMAIN/MCP_PATH, client secret и ролей также требуют обновления существующего realm через Admin API/CLI; не удаляйте PostgreSQL ради обновления.

## Сертификаты и диагностика

Certbot работает в Docker, при старте и каждые 12 часов вызывает стандартный renew. После успешного обновления deploy hook посылает сигнал Nginx; reload происходит примерно в течение 30 секунд. Сохраняются HTTP-01 webroot, отключение буферизации SSE и исходные пути ToolHub.

```bash
docker compose ps
docker compose logs --tail=100 nginx certbot keycloak auth-gate postgres
curl -i https://tools.your-domain.net/.well-known/oauth-protected-resource
curl -i https://tools.your-domain.net/mcp
```

Первый URL возвращает JSON metadata, второй без токена должен вернуть 401 и WWW-Authenticate. Убедитесь, что OpenID discovery содержит `code_challenge_methods_supported` с S256, `authorization_response_iss_parameter_supported=true` и правильный HTTPS issuer. Проверьте полный вход в ChatGPT: это одновременно проверяет callback, обмен кода, aud и tool call.

Тест продления:

```bash
docker compose stop certbot
docker compose run --rm certbot renew --dry-run --run-deploy-hooks --deploy-hook /usr/local/bin/notify-nginx
docker compose up -d certbot
```

Даже после неудачного теста верните контейнер certbot. При ошибке deploy этап сертификата/HTTPS не продолжается; после исправления повторите deploy.sh.

## Требования и хранение

- DNS A указывает на сервер; при AAAA проверьте IPv6 для контейнерных портов.
- TCP 80/443 свободны и доступны извне, порт 80 нужен также для продления.
- На сервере достаточно памяти для JVM Keycloak и PostgreSQL в дополнение к ToolHub.
- Интернет требуется при сборке/pull и для Certbot ACME. OAuth-сервисы после запуска общаются по внутренним сетям.
- Общая сеть роутера должна сохраняться в его Compose после пересоздания. Nginx перечитывает upstream DNS при reload; после смены IP ToolHub выполните reload.

Постоянные данные: `data/letsencrypt`, `data/webroot`, `data/reload`, `data/certbot-work`, `data/certbot-logs`, **data/postgres**, data/keycloak-import и **config**. Data имеет права 0700 на хосте. Realm import содержит первичный пароль и Client Secret и нужен Keycloak при первом старте; его локальный доступ ограничен родительским data. Nginx получает сертификаты/challenge/сигнал только для чтения. Docker socket не монтируется.

Сохраняйте резервную копию config и сертификатов. PostgreSQL резервируйте штатным pg_dump:

```bash
docker compose exec -T postgres pg_dump -U keycloak keycloak > keycloak-backup.sql
```

Резервная копия содержит чувствительные данные. После успешного deploy обычные `docker compose down` и `docker compose up -d` сохраняют состояние. На первом запуске требуется deploy.sh.

## Миграция с 0.2.0

Перенесите `data/letsencrypt` целиком (с symlinks/archive), challenge/work/logs и параметры .env в новую директорию. Остановите прежний Compose project перед запуском нового: name/порты совпадают. Выполните deploy.sh; он создаст OAuth-сервисы. Начиная с этой версии, внешний доступ к ToolHub требует OAuth-токен.

Старые записи refresh/client в ChatGPT нужно переподключить с OAuth. Если ранее Certbot использовал host hooks или другой authenticator, настройте webroot и удалите несуществующие host hooks из перенесённых renewal-настроек до миграции.

## Проверка сборки

```bash
python3 -m pip install -r auth-gate/requirements.txt
python3 -m unittest discover -s tests -v
```

Прошли 22 теста: прежние сценарии deploy, HTTP metadata/challenge, настоящие RS256/JWKS-подписи, audience/issuer/expiry, ID-token/другой клиент, scopes/роли и конфигурация PKCE. Проверены shell и YAML. В среде подготовки Docker не установлен: **полный запуск Keycloak/PostgreSQL/Nginx и реальная авторизация ChatGPT не проверены**. После развёртывания выполните проверки выше.

## Источники

- https://developers.openai.com/plugins/build/auth
- https://developers.openai.com/api/docs/guides/custom-mcp-server
- https://www.keycloak.org/securing-apps/mcp-authz-server
- https://www.keycloak.org/server/containers
- https://www.keycloak.org/server/reverseproxy
- https://www.keycloak.org/server/importExport
- https://nginx.org/en/docs/http/ngx_http_auth_request_module.html
- https://pyjwt.readthedocs.io/en/stable/usage.html
