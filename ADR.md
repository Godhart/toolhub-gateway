# Архитектурные решения — 0.3.0

1. OAuth реализует Keycloak, состояние хранится в PostgreSQL. Собственный authorization server не создаётся.
2. Для ChatGPT используется предварительно зарегистрированный confidential клиент, PKCE S256 и точный redirect URI. Это обходит отмеченную Keycloak несовместимость CIMD; публичная DCR не используется.
3. Включён resource-indicators с resource_url MCP-клиента и audience mapper RP. Функция Keycloak экспериментальная, версия закреплена.
4. Nginx auth_request проверяет Bearer access token через внутренний Python/PyJWT сервис; потоковые запросы ToolHub продолжают проксироваться штатно.
5. Проверяются подпись, issuer, audience, срок, client, scope и роль. Подпись берётся только из настроенного JWKS. Онлайн-интроспекция не применяется; TTL access token 5 минут.
6. Discovery и вход доступны публично; админ-API Keycloak и master realm не публикуются. Инструменты ToolHub закрыты целиком, включая UI.
7. Nginx/Certbot контейнеры и прежнее продление сохранены. Docker socket не монтируется; reload происходит по атомарному сигналу.
8. Секреты генерируются один раз при первом deploy; realm import не перезаписывает существующую БД. Для изменений существующего клиента предусмотрены CLI helpers.
