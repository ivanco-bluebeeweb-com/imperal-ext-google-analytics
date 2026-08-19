# Scenario Tests (PST) — Google Analytics

Метод: `Docs/session-notes/SCENARIO_TESTING_STANDARD.md`.

---

## Прогон 2026-08-20 — Часть D (Deploy Verification / Idempotency / Security-SSRF / Regression grep)

**D1 (Deploy Verification):** не применялось — код приложения не менялся (только тесты), деплой не требуется.

**D2 (Idempotency):** добавлены 3 теста. `delete_alert_rule` уже был fail-closed (`store.get` перед delete) — тест подтверждает: второй вызов подряд получает чистую ошибку `GA4_ALERT_NOT_FOUND`, не падает. `disconnect_google_account` резолвит аккаунт через `resolve_account` перед удалением — второй вызов на уже отключённом аккаунте корректно не находит его и возвращает ошибку. `debug_purge_unresolved_accounts` подтверждён естественно идемпотентным — второй вызов находит ноль "битых" записей и возвращает пустой результат без ошибки.

**D3 (Security/SSRF):** ни одна `@chat.function` не принимает пользовательский URL — все обращения в `ga4_client.py`'s `request()` идут через два жёстко заданных константных хоста (`ADMIN_API`/`DATA_API`, оба `*.googleapis.com`). Добавлен 1 regression-тест, фиксирующий эти константы как trip-wire: если в будущем появится функция, принимающая сырой `url` и передающая его в `request()`, этот тест должен быть пересмотрен вместе с добавлением настоящего SSRF-теста.

**D4 (Regression grep):** нет новых находок специфичных для этого приложения сверх `Docs/known-bug-patterns.md`.

**Итог:** 123/123 тестов зелёные (было 118). Реальных багов не найдено.

---

## Прогон 2026-08-19

**Существующее покрытие до PST:** 104 теста в 13 файлах, широкое покрытие
всех веток (admin, alerts, reports, accounts, panels, pricing).
Предыдущий сквозной пост-аудит уже подтвердил приложение CLEAN (59
функций, 8 `destructive`, никакого double-prompt антипаттерна). Аудит по
точному имени функции (вызывается ли оно хоть в одном тесте где-либо)
нашёл **12 функций, никогда не тестировавшихся**:

- Отчёты (Part A): `get_top_referrers`, `get_landing_pages_report`,
  `get_conversions_report`, `get_ecommerce_overview`, `get_geo_breakdown`,
  `get_device_breakdown`, `get_campaign_performance`
- Алерты (Part C): `create_alert_rule`, `list_alert_rules`,
  `delete_alert_rule` (**destructive**)
- Admin: `list_properties`
- Диагностика: `debug_dump_raw_accounts`, `debug_purge_unresolved_accounts`

**Новый файл:** `tests/test_pst_scenarios.py` — 15 сценариев, целенаправленно
закрывающих именно эти 12 функций: happy path для каждого canned-отчёта,
полный жизненный цикл alert rule (create → list → delete, единственная
`destructive` функция в пробеле — проверена end-to-end, включая
подтверждение реального исчезновения после удаления), `list_properties`
happy/error, оба diagnostic-хелпера (включая проверку, что purge удаляет
ТОЛЬКО записи без usable email, никогда реально подключённый аккаунт).

### Результат

119/119 тестов зелёные (104 существующих + 15 новых). **Реальных багов в
приложении не найдено.**

Две собственные ошибки в черновике PST, обе исправлены:
1. Неверное имя метода GA4-клиента в моке (`ga4.run_report` вместо
   реального `ga4.report`).
2. `create_alert_rule` дополнительно вызывает `ga4.properties()` после
   `resolve_account()` для проверки, что property действительно доступен
   этому аккаунту — не замокала это на первом заходе, из-за чего тест
   ловил настоящую сетевую попытку и `TOKEN_REJECTED`. Добавлен мок.

---
