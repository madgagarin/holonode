[EN](https://github.com/madgagarin/holonode/blob/main/SECURITY.md) | **ES** | [RU](https://github.com/madgagarin/holonode/blob/main/docs/ru/SECURITY.md)

# Política de Seguridad

## Informar una Vulnerabilidad

Si descubre una vulnerabilidad de seguridad potencial en el Worker SDK, por favor no abra un Issue público. En su lugar, envíe un correo electrónico a madgagarin@gmail.com.

## Modelo de Seguridad

El SDK del Worker es un nodo de ejecución clave en la **Red Lógica Holárquica (HLN)** y el ecosistema de Holarchy, diseñado con principios Zero Trust y de seguridad primero:

1. **TLS Mutuo (mTLS)**: Admite certificados de cliente para una comunicación segura y autenticada con el Orquestador.
2. **Rotación Dinámica de Tokens**: Maneja automáticamente la actualización de los tokens de acceso STS sin necesidad de reiniciar el worker.
3. **Aislamiento Estricto**: Cada tarea opera en su propio directorio temporal aislado (`TASK_FILES_DIR`). Los datos de una tarea no pueden ser accedidos por otra.
4. **Protección contra Path Traversal**: Control estricto de rutas de archivos para evitar accesos fuera del directorio asignado a la tarea.
5. **Limpieza Automática**: Los datos temporales y archivos `.tmp_*` se eliminan de forma segura inmediatamente después de la finalización o fallo de la tarea.
6. **Protección de Datos Sensibles**: Las credenciales de S3 y los tokens del orquestador se manejan exclusivamente a través de variables de entorno o configuraciones seguras, nunca se registran en los logs.
7. **Integridad de Mensajes (HMAC-SHA256)**: El worker firma automáticamente todos los mensajes salientes (heartbeats, resultados, eventos) con su token, evitando la manipulación de datos en tránsito.
8. **Verificación de Firma de Tareas Entrantes**: Valida las firmas criptográficas HMAC-SHA256 (`sig` / `orchestrator_signature`) de las tareas entrantes mediante `ORCHESTRATOR_SECRET_KEY`.
9. **Cumplimiento de Políticas de Ejecución**: Verifica que las tareas cumplan con las restricciones de habilidades permitidas (`allowed_skills`).
10. **Protección contra Repetición (Replay Protection)**: Todos los mensajes firmados contienen una marca de tiempo (`timestamp`). El orquestador rechaza paquetes caducados o repetidos.

Consulte el [Modelo de Seguridad RXON / HLN](https://github.com/madgagarin/rxon/blob/main/SECURITY.md) y la [Política de Seguridad de Holarchy](https://github.com/madgagarin/holarchy/blob/main/SECURITY.md) para obtener detalles sobre todo el ecosistema.
