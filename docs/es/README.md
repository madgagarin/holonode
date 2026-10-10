[EN](https://github.com/madgagarin/holonode/blob/main/README.md) | **ES** | [RU](https://github.com/madgagarin/holonode/blob/main/docs/ru/README.md)

# Holonode SDK

[![Licencia: MPL 2.0](https://img.shields.io/badge/License-MPL%202.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)
[![Versión de PyPI](https://img.shields.io/pypi/v/holonode.svg)](https://pypi.org/project/holonode/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/release/python-3110/)

**Holonode SDK** es el SDK oficial de alto rendimiento en Python para construir nodos de ejecución distribuidos (Workers / Holones) compatibles con el orquestador **Holarchy**. Actúa como nodo de ejecución (**Cáscara / Shell**) en una **Red Lógica Holárquica (HLN)**, coordinándose con el orquestador (**Fantasma / Ghost**) a través del protocolo **RXON** (Reverse Axon Protocol).

El SDK automatiza todas las tareas de bajo nivel: sondeo de tareas (polling), registro dinámico, latidos (heartbeats), gestión de datos pesados en S3, autenticación Zero Trust y cierre ordenado (graceful shutdown).

## 🚀 Características Principales

- **Lenguaje:** Python 3.11+
- **Protocolo:** Soporte nativo para **RXON** (Reverse Axon Protocol) en **HLN** (Red Lógica Holárquica / Holarchical Logic Network).
- **Modelo de Comunicación:**
  - **PULL:** Los trabajadores sondean tareas desde los orquestadores (funciona de forma segura detrás de NAT/Firewall sin puertos de entrada públicos).
  - **WebSocket:** Canal bidireccional opcional en tiempo real para comandos y cancelación inmediata.
- **Seguridad Zero Trust y Capa de Políticas:**
  - Firma HMAC-SHA256 obligatoria para todos los mensajes del worker mediante `WORKER_TOKEN`.
  - Verificación criptográfica de la firma del orquestador (`orchestrator_signature` / `sig`) en tareas entrantes mediante `ORCHESTRATOR_SECRET_KEY`.
  - Aplicación estricta de políticas de ejecución de tareas (`allowed_skills`).
  - Recopilación y reporte automático de métricas de costo y tiempo de ejecución (`costs`).
  - Soporte de cadenas de identidad (Identity Chain) y Origin Worker ID para rastreo de procedencia a través de infinitas capas de holarquía.
  - Protección contra ataques de repetición (Replay Protection) con marcas de tiempo obligatorias.
- **Optimización de Tráfico y Rendimiento:**
  - **Telemetry Throttling (Heartbeat Deadband):** La telemetría de hardware (CPU/RAM/GPU) solo se transmite cuando el valor varía en >5% o tras un intervalo forzado de 60s, ahorrando ancho de banda.
  - **Caché de Blobs basada en ETag:** Los archivos grandes (ej. pesos de modelos de IA) se descargan de S3 solo una vez, se almacenan en caché local y se enlazan con el espacio de trabajo de la tarea mediante enlaces simbólicos.
  - **Subida de Resultados Asíncrona:** Los resultados se encolan mediante un `asyncio.Queue` no bloqueante con reintentos automáticos y backoff exponencial, liberando de inmediato al worker.
  - **Ciclo de Vida de Habilidades en 3 Niveles:** _Supported_ (catálogo completo), _Available_ (límites dinámicos) y _Hot_ (precargadas en memoria/VRAM).
  - **Stable Hashing:** Envío del catálogo completo solo cuando hay cambios mediante `skills_hash`.
- **S3 Streaming:** Transmisión de datos de alto rendimiento mediante `obstore`. Cero errores de falta de memoria (OOM) en archivos gigantes.
- **Soporte para Agentes de IA:** Soporte para razonamiento y uso de herramientas (Tool Use / Chain of Thought) mediante la inyección del cliente `OrchestratorClient`.
- **Monitoreo de Hardware:** Monitoreo integrado de CPU, memoria RAM y GPUs NVIDIA (mediante `psutil` y `GPUtil`).
- **Observabilidad Moderna:**
  - Trazado distribuido y métricas nativas con **OpenTelemetry**.
  - **Propagación Automática de Contexto de Rastreo:** Extrae el `trace_id` de las tareas y lo propaga a todos los eventos y sub-spans.
  - Exportación de métricas push vía OTLP mediante `OTEL_EXPORTER_OTLP_ENDPOINT`.

## Tabla de Contenidos

- [Arquitectura Central: Orquestadores y Workers](#arquitectura-central-orquestadores-y-workers)
- [Ecosistema](#ecosistema)
- [Instalación](#instalación)
- [Inicio Rápido](#inicio-rápido)
  - [Uso como Librería](#uso-como-librería)
  - [Uso mediante CLI](#uso-mediante-cli)
- [Referencia de Configuración](#referencia-de-configuración)
- [Resiliencia y Conectividad](#resiliencia-y-conectividad)
- [Observabilidad](#observabilidad)
- [Seguridad](#seguridad)
- [Contribución](#contribución)
- [Licencia](#licencia)

## Arquitectura Central: Orquestadores y Workers

Holonode SDK implementa la capa de ejecución de una **Red Lógica Holárquica (HLN)**:

- **Orquestador**: Gestiona las máquinas de estado de flujos de trabajo (Blueprints), rastrea el ciclo de vida de los trabajos y coordina tareas. Opera como un servidor HTTP pasivo y no inicia conexiones salientes hacia los workers.
- **Worker**: Nodo de ejecución autónomo. Se conecta al orquestador mediante sondeo inverso por HTTP, registra habilidades y recursos disponibles, extrae tareas asignadas hacia espacios de trabajo aislados y publica resultados de forma asíncrona.
- **Composición Jerárquica**: Los contratos estandarizados permiten envolver una instancia de orquestador dentro de la interfaz de un worker, habilitando la delegación recursiva de tareas en clústeres distribuidos.

## Ecosistema

Holonode SDK es parte integral del ecosistema distribuido de Holarchy:

- **[Orquestador Holarchy](https://github.com/madgagarin/holarchy)**: Motor de flujos de trabajo de alto rendimiento basado en máquinas de estados para coordinar tareas y blueprints distribuidos.
- **[Protocolo RXON](https://github.com/madgagarin/rxon)**: Protocolo compartido de conexión inversa ligera para la comunicación entre nodos en la red HLN.
- **[HLN (Holarchical Logic Network)](https://github.com/madgagarin/hln)**: Patrón arquitectónico, manifiesto y especificación de diseño para holarquías autosimilares.
- **[SDK de Worker de Holarchy](https://github.com/madgagarin/holonode)**: SDK oficial de Python para construir trabajadores de ejecución (este repositorio).
- **[Ejemplo Completo (Full Example)](https://github.com/madgagarin/holarchy-full-example)**: Proyecto de referencia completo que demuestra el motor y los workers en acción.

## Instalación

- **Instalar solo el SDK principal:**

  ```bash
  pip install holonode
  ```

- **Instalar con soporte para descarga de archivos en S3:**

  ```bash
  pip install "holonode[s3]"
  ```

- **Instalar con validación de esquemas vía Pydantic v2:**

  ```bash
  pip install "holonode[pydantic]"
  ```

- **Instalar con métricas y trazado OpenTelemetry:**

  ```bash
  pip install "holonode[metrics]"
  ```

- **Instalar todas las funciones de producción (Recomendado):**

  ```bash
  pip install "holonode[s3,pydantic,metrics]"
  ```

- **Instalar para desarrollo:**

  ```bash
  pip install -e ".[dev]"
  ```

## Inicio Rápido

### Uso como Librería

```python
from pydantic import BaseModel, Field
from holonode import OrchestratorClient, TaskFiles, Worker


class GreetingParams(BaseModel):
    nombre: str = Field(default="Mundo", description="Nombre para el saludo")


worker = Worker(worker_type="greeter-service")


@worker.skill("hola_mundo", risk="low", permissions=["greetings:write"])
async def mi_habilidad(params: GreetingParams, files: TaskFiles):
    """El SDK valida automáticamente los datos de la tarea contra GreetingParams."""
    return {"message": f"¡Hola, {params.nombre}!"}


@worker.skill("ai_agent_reasoning", risk="medium", permissions=["ai:reason"])
async def agent_skill(params: dict, orchestrator_client: OrchestratorClient):
    """Habilidad de agente de IA que delega una subtarea (Tool Use) vía OrchestratorClient."""
    search_result = await orchestrator_client.call_skill("web_search", {"query": params["search_query"]})
    return {"result": f"Basado en búsqueda web: {search_result['data']}"}


@worker.on_command("reiniciar")
async def manejar_reinicio(comando: dict):
    """Comando personalizado recibido en tiempo real por el canal WebSocket."""
    print("Reiniciando trabajador...")


if __name__ == "__main__":
    worker.run()
```

> Para una guía paso a paso, consulte el [Libro de recetas: Desarrollo local de workers](https://github.com/madgagarin/holarchy/blob/main/docs/es/cookbook/local_worker_development.md).

### Uso mediante CLI

El SDK incluye una herramienta CLI para gestionar workers, inspeccionar habilidades y depurar localmente:

```bash
# Ejecutar el worker con servidor de comprobación de salud (puerto 8083 por defecto)
worker run --app my_worker:worker

# Ejecutar con panel TUI (HUD) en tiempo real en la terminal
worker run --app my_worker:worker --hud

# Ejecutar en un puerto personalizado sin servidor de comprobación de salud
worker run --app my_worker:worker --port 9000 --no-health-check

# Modo de desarrollo con recarga automática al modificar el código
worker run --app my_worker:worker --reload

# Ejecutar una habilidad localmente en un entorno aislado (sin necesidad de orquestador)
worker exec --app my_worker:worker --skill hola_mundo --params '{"nombre": "Alicia"}'
worker exec --app my_worker:worker --skill hola_mundo --params @params.json

# Inspeccionar habilidades registradas, niveles de riesgo y permisos
worker inspect --app my_worker:worker
worker inspect --app my_worker:worker --json
worker inspect --app my_worker:worker --skill hola_mundo

# Iniciar banco de pruebas web local para depuración manual de habilidades
worker dev --app my_worker:worker --port 8088
```

## Referencia de Configuración

Todos los parámetros pueden configurarse mediante variables de entorno:

| Variable | Tipo | Predeterminado | Descripción |
| :--- | :---: | :---: | :--- |
| `ORCHESTRATOR_URL` | String | `http://localhost:8080` | URL del orquestador si solo se utiliza uno |
| `ORCHESTRATORS_CONFIG` | JSON String | `None` | Lista JSON de configuraciones de múltiples orquestadores (`url`, `priority`, `weight`) |
| `MULTI_ORCHESTRATOR_MODE` | String | `WATERFALL` | Estrategia de sondeo: `WATERFALL` (por prioridad) o `ROUND_ROBIN` (secuencial sin pausas) |
| `WORKER_ID` | String | Autogenerado | Identificador único de la instancia del worker |
| `WORKER_TYPE` | String | `generic-cpu-worker` | Etiqueta de tipo para emparejamiento de habilidades |
| `WORKER_PORT` | Integer | `8083` | Puerto para la sonda de verificación HTTP (`/health`) |
| `WORKER_ENABLE_HUD` | Boolean | `False` | Habilitar panel de estado TUI (HUD) en la terminal |
| `WORKER_TOKEN` | String | `None` | Token secreto para la firma obligatoria HMAC-SHA256 de mensajes (Zero Trust) |
| `ORCHESTRATOR_SECRET_KEY` | String | `None` | Clave secreta para verificar la firma de tareas entrantes del orquestador (`sig`) |
| `REQUIRE_TASK_SIGNATURE` | Boolean | `True` | Exigir firma válida en tareas entrantes si la clave secreta está configurada |
| `COST_PER_SKILL` | JSON String | `None` | Diccionario JSON de tarifas de ejecución de habilidades (ej. `'{"render": 0.05}'`) |
| `MAX_CONCURRENT_TASKS` | Integer | `None` | Límite global de tareas ejecutadas en paralelo |
| `WORKER_ENABLE_WEBSOCKETS` | Boolean | `True` | Habilitar canal WebSocket en tiempo real para comandos y cancelaciones |
| `S3_ENDPOINT_URL` | String | `None` | URL de endpoint de almacenamiento compatible con S3 |
| `S3_ACCESS_KEY` | String | `None` | ID de clave de acceso a S3 |
| `S3_SECRET_KEY` | String | `None` | Clave secreta de acceso a S3 |
| `S3_DEFAULT_BUCKET` | String | `None` | Bucket de S3 predeterminado para la transferencia de archivos |
| `WORKER_BLOB_CACHE_DIR` | String | `/tmp/holarchy_cache` | Directorio local de caché de blobs de S3 con verificación ETag |
| `TASK_FILES_DIR` | String | `/tmp/payloads` | Directorio base para los archivos de la tarea aislada |
| `WORKER_TELEMETRY_DEADBAND` | Float | `5.0` | Umbral de cambio (%) para el envío de telemetría de hardware |
| `WORKER_TELEMETRY_FORCE_INTERVAL` | Float | `60.0` | Intervalo máximo (segundos) antes de forzar el envío de telemetría |
| `POLL_BACKOFF_INITIAL` | Float | `1.0` | Retraso inicial (segundos) tras un error de red o código 429 |
| `POLL_BACKOFF_MAX` | Float | `60.0` | Retraso máximo del backoff exponencial (segundos) |
| `POLL_BACKOFF_FACTOR` | Float | `2.0` | Multiplicador para el cálculo del backoff exponencial |
| `STRICT_EVENT_VALIDATION` | Boolean | `True` | Validar eventos emitidos contra los esquemas del protocolo |
| `LOG_LEVEL` | String | `INFO` | Nivel de detalle de los registros (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## Resiliencia y Conectividad

- **Gestores de Orquestadores Independientes:** La conexión con cada orquestador se gestiona en una tarea en segundo plano aislada. Problemas con un servidor nunca bloquean a los demás.
- **Backoff Inteligente y Protección contra Tormentas de Reintentos:** El backoff exponencial respeta el encabezado HTTP `Retry-After` (segundos o fecha HTTP). Los errores 429 sin `Retry-After` imponen un «piso de seguridad» obligatorio de 30 segundos.
- **Heartbeat Debouncing:** Los latidos se limitan a un máximo de uno cada 2 segundos. Los eventos intermedios se acumulan y se envían agrupados.
- **Graceful Shutdown:** Captura limpiamente las señales `SIGINT` y `SIGTERM`, esperando la finalización de las tareas activas y notificando a los orquestadores antes de salir.

## Observabilidad

Holonode SDK proporciona observabilidad de primer nivel utilizando el estándar **OpenTelemetry**:

- **Trazado Distribuido:** Los workers extraen el `trace_id` de las tareas y crean spans hijos (`task.{type}`). Todos los eventos y operaciones con S3 comparten el mismo contexto.
- **Métricas Push OTLP:** Al configurar la variable `OTEL_EXPORTER_OTLP_ENDPOINT`, las métricas se envían directamente al recolector OTLP.
- **Inyección de ObservabilityManager:** Los manejadores pueden recibir `obs: ObservabilityManager` para generar spans personalizados e incluir metadatos de diagnóstico.

## Seguridad

La seguridad es un pilar fundamental en todo el ecosistema de Holarchy:

- Consulte el [Modelo de Seguridad RXON / HLN](https://github.com/madgagarin/rxon/blob/main/SECURITY.md).
- Consulte la [Política de Seguridad de Holarchy](https://github.com/madgagarin/holarchy/blob/main/SECURITY.md).
- Las políticas de seguridad detalladas del worker se encuentran en [SECURITY.md](https://github.com/madgagarin/holonode/blob/main/docs/es/SECURITY.md).

## Contribución

¡Agradecemos sus contribuciones! Por favor revise nuestra [Guía para Contribuidores](https://github.com/madgagarin/holonode/blob/main/docs/es/CONTRIBUTING.md) y la [Guía de Desarrollo](https://github.com/madgagarin/holonode/blob/main/docs/es/DEVELOPMENT.md) para conocer la configuración del entorno y las pruebas.

## Licencia

Este proyecto está bajo la licencia **Mozilla Public License 2.0 (MPL 2.0)**.
