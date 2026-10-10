[EN](https://github.com/madgagarin/holonode/blob/main/README.md) | [ES](https://github.com/madgagarin/holonode/blob/main/docs/es/README.md) | **RU**

# Holonode SDK

[![Лицензия: MPL 2.0](https://img.shields.io/badge/License-MPL%202.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)
[![Версия PyPI](https://img.shields.io/pypi/v/holonode.svg)](https://pypi.org/project/holonode/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/release/python-3110/)

**Holonode SDK** — это официальный высокопроизводительный Python SDK для создания распределенных узлов исполнения (воркеров / холонов), совместимых с оркестратором **Holarchy**. Он выступает в роли исполнительного узла (**Оболочки / Shell**) в **Холархической Логической Сети (HLN)**, координируясь с оркестратором (**Призраком / Ghost**) через протокол **RXON** (Reverse Axon Protocol).

SDK автоматизирует все низкоуровневые сетевые задачи: опрос задач (polling), динамическую регистрацию, пульс (heartbeats), управление тяжелыми данными в S3, Zero Trust аутентификацию и корректное завершение работы (graceful shutdown).

## 🚀 Основные возможности

- **Язык:** Python 3.11+
- **Протокол:** Нативная поддержка **RXON** (Reverse Axon Protocol) для **HLN** (Холархическая логическая сеть / Holarchical Logic Network).
- **Модель взаимодействия:**
  - **PULL:** Воркер сам опрашивает задачи у оркестраторов (безопасно работает за NAT/Firewall без необходимости открывать входящие порты).
  - **WebSocket:** Опциональный двунаправленный канал для команд в реальном времени (отмена задач, управляющие команды).
- **Zero Trust Security & Слой политик:**
  - Обязательная криптографическая подпись HMAC-SHA256 для всех сообщений воркера при наличии `WORKER_TOKEN`.
  - Проверка подписи оркестратора (`orchestrator_signature` / `sig`) входящих задач перед выполнением через `ORCHESTRATOR_SECRET_KEY`.
  - Строгое соблюдение политик выполнения задач (`allowed_skills`).
  - Автоматический сбор и передача метрик затрат и времени исполнения задач (`costs`).
  - Поддержка цепочек идентичности (Identity Chain) и Origin Worker ID для сквозного отслеживания происхождения данных через любые уровни холархии.
  - Защита от атак повтора (Replay Protection) через обязательные временные метки.
- **Оптимизация трафика и производительности:**
  - **Telemetry Throttling (Heartbeat Deadband):** Телеметрия ресурсов (CPU/RAM/GPU) передается только при изменении значений более чем на 5% или раз в 60 сек, существенно экономя трафик.
  - **ETag-кэширование блобов:** Тяжелые файлы (например, веса нейросетей) скачиваются из S3 один раз, кэшируются локально с проверкой ETag и монтируются в рабочую папку через симлинки.
  - **Асинхронный uploader результатов:** Результаты отправляются через неблокирующую очередь `asyncio.Queue` с авторетриями и экспоненциальной задержкой, мгновенно освобождая воркер для следующей задачи.
  - **3-уровневый жизненный цикл навыков:** _Supported_ (каталог), _Available_ (динамические лимиты) и _Hot_ (предзагруженные в RAM/VRAM).
  - **Stable Hashing:** Передача полного каталога навыков только при фактических изменениях по хешу `skills_hash`.
- **S3 Streaming:** Потоковая передача данных через `obstore` без риска исчерпания оперативной памяти (OOM) на больших файлах.
- **Интеграция с ИИ-агентами:** Поддержка логических цепочек (Chain of Thought / Tool Use) через внедрение клиента `OrchestratorClient` для синхронного или асинхронного вызова инструментов.
- **Мониторинг железа:** Встроенный сбор метрик CPU, RAM и видеокарт NVIDIA (через `psutil` и `GPUtil`).
- **Современная наблюдаемость (Observability):**
  - Нативная поддержка **OpenTelemetry** (трассировка и метрики).
  - Автоматический **проброс контекста трассировки**: извлечение `trace_id` из задачи и инжекция во все генерируемые события и дочерние спаны.
  - Экспорт метрик по OTLP (Push-модель) при указании `OTEL_EXPORTER_OTLP_ENDPOINT`.

## Оглавление

- [Архитектура: Оркестраторы и Воркеры](#архитектура-оркестраторы-и-воркеры)
- [Экосистема](#экосистема)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
  - [Использование в качестве библиотеки](#использование-в-качестве-библиотеки)
  - [Использование через CLI](#использование-через-cli)
- [Справочник конфигурации](#справочник-конфигурации)
- [Отказоустойчивость и связность](#отказоустойчивость-и-связность)
- [Наблюдаемость](#наблюдаемость)
- [Безопасность](#безопасность)
- [Участие в разработке](#участие-в-разработке)
- [Лицензия](#лицензия)

## Архитектура: Оркестраторы и Воркеры

Holonode SDK реализует исполнительный уровень архитектуры **HLN (Holarchical Logic Network)**:

- **Оркестратор**: Управляет графами состояний бизнес-процессов (Blueprints), отслеживает жизненный цикл задач и распределяет нагрузку. Оркестратор работает как пассивный HTTP-сервис и не открывает исходящих сетевых соединений к воркерам.
- **Воркер**: Автономный исполнительный узел. Подключается к оркестратору по модели обратного опроса через HTTP, регистрирует поддерживаемые навыки и доступные ресурсы, получает назначенные задачи, исполняет их в изолированных каталогах и асинхронно передает результаты.
- **Иерархическая композиция**: Стандартизированные протокольные контракты позволяют обернуть экземпляр оркестратора в интерфейс воркера, организуя многоуровневое рекурсивное делегирование задач в распределенных кластерах.

## Экосистема

Holonode SDK является ключевой частью распределенной экосистемы:

- **[Оркестратор Holarchy](https://github.com/madgagarin/holarchy)**: Высокопроизводительный движок рабочих процессов на конечных автоматах, координирующий распределенные задачи.
- **[Протокол RXON](https://github.com/madgagarin/rxon)**: Легковесный протокол обратного соединения, обеспечивающий защищенное межмашинное взаимодействие в сети HLN.
- **[HLN (Holarchical Logic Network)](https://github.com/madgagarin/hln)**: Архитектурный манифест и спецификация самоподобных холархий.
- **[Holonode SDK](https://github.com/madgagarin/holonode)**: Официальный SDK на Python для создания исполнительных воркеров (текущий репозиторий).
- **[Полный пример (Full Example)](https://github.com/madgagarin/holarchy-full-example)**: Готовый проект, демонстрирующий совместную работу оркестратора и воркеров.

## Установка

- **Установка только базового SDK:**

  ```bash
  pip install holonode
  ```

- **Установка с поддержкой работы с файлами в S3:**

  ```bash
  pip install "holonode[s3]"
  ```

- **Установка с валидацией схем через Pydantic v2:**

  ```bash
  pip install "holonode[pydantic]"
  ```

- **Установка с поддержкой телеметрии OpenTelemetry:**

  ```bash
  pip install "holonode[metrics]"
  ```

- **Установка всех производственных компонентов (Рекомендуется):**

  ```bash
  pip install "holonode[s3,pydantic,metrics]"
  ```

- **Установка для разработки:**

  ```bash
  pip install -e ".[dev]"
  ```

## Быстрый старт

### Использование в качестве библиотеки

```python
from pydantic import BaseModel, Field
from holonode import OrchestratorClient, TaskFiles, Worker


class GreetingParams(BaseModel):
    name: str = Field(default="Мир", description="Имя для приветствия")


worker = Worker(worker_type="greeter-service")


@worker.skill("hello_world", risk="low", permissions=["greetings:write"])
async def my_skill(params: GreetingParams, files: TaskFiles):
    """SDK автоматически валидирует входные данные в GreetingParams."""
    return {"message": f"Привет, {params.name}!"}


@worker.skill("ai_agent_reasoning", risk="medium", permissions=["ai:reason"])
async def agent_skill(params: dict, orchestrator_client: OrchestratorClient):
    """Навык ИИ-агента, делегирующий подзадачу (Tool Use) через OrchestratorClient."""
    search_result = await orchestrator_client.call_skill("web_search", {"query": params["search_query"]})
    return {"result": f"Результат веб-поиска: {search_result['data']}"}


@worker.on_command("reboot")
async def handle_reboot(command: dict):
    """Пользовательская команда, принятая по каналу WebSocket в реальном времени."""
    print("Перезагрузка воркера...")


if __name__ == "__main__":
    worker.run()
```

> Пошаговое руководство см. в [Рецепте локальной разработки воркеров](https://github.com/madgagarin/holarchy/blob/main/docs/ru/cookbook/local_worker_development.md).

### Использование через CLI

В SDK встроен CLI для управления воркерами, локальной отладки и проверки навыков:

```bash
# Запуск воркера с сервером health-check (порт 8083 по умолчанию)
worker run --app my_worker:worker

# Запуск с терминальным TUI-дашбордом (HUD) в реальном времени
worker run --app my_worker:worker --hud

# Запуск на выделенном порту без сервера health-check
worker run --app my_worker:worker --port 9000 --no-health-check

# Режим разработки с автоперезагрузкой при изменении кода
worker run --app my_worker:worker --reload

# Локальный запуск навыка в изолированной песочнице (без подключения к оркестратору)
worker exec --app my_worker:worker --skill hello_world --params '{"name": "Алиса"}'
worker exec --app my_worker:worker --skill hello_world --params @params.json

# Инспекция зарегистрированных навыков, уровней риска и прав доступа
worker inspect --app my_worker:worker
worker inspect --app my_worker:worker --json
worker inspect --app my_worker:worker --skill hello_world

# Запуск локального веб-стенда для тестирования навыков через браузер
worker dev --app my_worker:worker --port 8088
```

## Справочник конфигурации

Все параметры могут настраиваться через переменные окружения:

| Переменная | Тип | По умолчанию | Описание |
| :--- | :---: | :---: | :--- |
| `ORCHESTRATOR_URL` | String | `http://localhost:8080` | URL одиночного оркестратора для подключения |
| `ORCHESTRATORS_CONFIG` | JSON String | `None` | JSON-список конфигураций нескольких оркестраторов (`url`, `priority`, `weight`) |
| `MULTI_ORCHESTRATOR_MODE` | String | `WATERFALL` | Стратегия опроса: `WATERFALL` (по приоритету) или `ROUND_ROBIN` (по весам без пауз) |
| `WORKER_ID` | String | Авто | Уникальный идентификатор экземпляра воркера |
| `WORKER_TYPE` | String | `generic-cpu-worker` | Тип воркера для таргетинга задач оркестратором |
| `WORKER_PORT` | Integer | `8083` | Порт встроенного HTTP health-check сервера (`/health`) |
| `WORKER_ENABLE_HUD` | Boolean | `False` | Включение терминального TUI-дашборда (HUD) |
| `WORKER_TOKEN` | String | `None` | Секретный токен для обязательной подписи сообщений воркера HMAC-SHA256 (Zero Trust) |
| `ORCHESTRATOR_SECRET_KEY` | String | `None` | Секретный ключ для верификации подписи входящих задач оркестратора (`sig`) |
| `REQUIRE_TASK_SIGNATURE` | Boolean | `True` | Требовать обязательную валидную подпись входящих задач при наличии секрета |
| `COST_PER_SKILL` | JSON String | `None` | JSON-словарь тарифов навыков для биллинга (например, `'{"render": 0.05}'`) |
| `MAX_CONCURRENT_TASKS` | Integer | `None` | Глобальный лимит на число одновременно выполняемых задач |
| `WORKER_ENABLE_WEBSOCKETS` | Boolean | `True` | Включить WebSocket для отмены задач и команд реального времени |
| `S3_ENDPOINT_URL` | String | `None` | URL эндпоинта S3-совместимого объектного хранилища |
| `S3_ACCESS_KEY` | String | `None` | Идентификатор ключа доступа к S3 |
| `S3_SECRET_KEY` | String | `None` | Секретный ключ доступа к S3 |
| `S3_DEFAULT_BUCKET` | String | `None` | Бакет S3 по умолчанию для передачи файлов задач |
| `WORKER_BLOB_CACHE_DIR` | String | `/tmp/holarchy_cache` | Директория локального кэширования S3 блобов с проверкой ETag |
| `TASK_FILES_DIR` | String | `/tmp/payloads` | Базовая директория для изолированных файлов исполняемой задачи |
| `WORKER_TELEMETRY_DEADBAND` | Float | `5.0` | Порог дельты телеметрии (%) для подавления избыточных хартбитов |
| `WORKER_TELEMETRY_FORCE_INTERVAL` | Float | `60.0` | Максимальный интервал (сек) принудительной отправки телеметрии |
| `POLL_BACKOFF_INITIAL` | Float | `1.0` | Начальная задержка (сек) при ошибках сети или статусе 429 |
| `POLL_BACKOFF_MAX` | Float | `60.0` | Максимальный потолок экспоненциальной задержки (сек) |
| `POLL_BACKOFF_FACTOR` | Float | `2.0` | Множитель экспоненциального бэкоффа |
| `STRICT_EVENT_VALIDATION` | Boolean | `True` | Проверка отправляемых событий на соответствие схеме протокола |
| `LOG_LEVEL` | String | `INFO` | Уровень детализации логов (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## Отказоустойчивость и связность

- **Изолированные менеджеры соединений:** Подключение к каждому оркестратору обслуживается отдельной фоновой задачей. Проблемы с доступностью одного сервера не влияют на работу с остальными.
- **Умный бэкофф и защита от Retry Storm:** Унифицированный экспоненциальный бэкофф учитывает заголовок `Retry-After` (в секундах или HTTP-дате). Для ошибок 429 без указания `Retry-After` применяется обязательный «пол безопасности» в 30 секунд.
- **Heartbeat Debouncing:** Пульс отправляется не чаще раза в 2 секунды. Промежуточные события не теряются, а агрегируются и отсылаются пачкой.
- **Graceful Shutdown:** Корректно перехватывает сигналы `SIGINT` и `SIGTERM`, ожидает завершения текущих задач и уведомляет оркестраторы перед остановкой.

## Наблюдаемость

Holonode SDK предоставляет полноценную поддержку стандарта **OpenTelemetry**:

- **Сквозная трассировка:** Воркер извлекает `trace_id` из задачи и создает дочерние спаны (`task.{type}`). Все события задачи и операции с S3 наследуют общий контекст.
- **Экспорт метрик OTLP:** При наличии переменной `OTEL_EXPORTER_OTLP_ENDPOINT` метрики пушатся напрямую в OTel Collector.
- **Инжекция ObservabilityManager:** В хендлеры можно внедрять параметр `obs: ObservabilityManager` для создания собственных спанов и фиксации детальной телеметрии.

## Безопасность

Безопасность является фундаментальным приоритетом:

- Ознакомьтесь с полной [Моделью безопасности RXON / HLN](https://github.com/madgagarin/rxon/blob/main/SECURITY.md).
- Ознакомьтесь с [Политикой безопасности Holarchy](https://github.com/madgagarin/holarchy/blob/main/SECURITY.md).
- Детальные политики безопасности воркера описаны в файле [SECURITY.md](https://github.com/madgagarin/holonode/blob/main/docs/ru/SECURITY.md).

## Участие в разработке

Мы приветствуем ваш вклад в развитие проекта! Ознакомьтесь с [Руководством контрибьютора](https://github.com/madgagarin/holonode/blob/main/docs/ru/CONTRIBUTING.md) и [Руководством разработчика](https://github.com/madgagarin/holonode/blob/main/docs/ru/DEVELOPMENT.md) для настройки окружения и запуска тестов.

## Лицензия

Проект распространяется под лицензией **Mozilla Public License 2.0 (MPL 2.0)**.
