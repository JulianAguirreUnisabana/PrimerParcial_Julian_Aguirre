# Emergency Control — Planificador Autónomo

**Nombre del estudiante:** Julián Santiago Aguirre Lara

## Introducción del proyecto

Este proyecto implementa un agente autónomo para restaurar los sistemas
críticos de una instalación experimental. El robot debe desplazarse entre zonas,
recoger recursos, abrir puertas, reparar paneles y activar las estaciones
`GENERATOR`, `COMMAND` y `ARTILLERY`.

El backend está construido con FastAPI y contiene el modelo del mundo, la
generación de acciones, la poda de estados y las búsquedas UCS y satisficiente.
El frontend, desarrollado con React, TypeScript, Vite y React Three Fiber,
visualiza la ejecución del plan en una simulación 3D.

El entorno es totalmente observable, determinista, secuencial, estático,
discreto y de agente único. La batería, la capacidad de carga, las puertas, los
materiales, los paneles y las dependencias entre estaciones forman parte de las
restricciones del problema.

## Resultados

- La API genera un plan válido para el escenario recibido.
- La búsqueda satisficiente resuelve el escenario completo en aproximadamente
        `1.1` segundos.
- El plan validado alcanza todas las estaciones objetivo en estado `ONLINE`.
- El resultado actual utiliza `39` pasos y un costo aproximado de `108` unidades
        de energía.
- El backend incluye pruebas de estados equivalentes, información relevante,
        costos diferentes, ausencia de solución, rutas alternativas y rendimiento.
- El estado se poda mediante canonicalización, compactación de objetos
        irrelevantes y dominancia por costo y batería.

## Guía de ejecución

Las instrucciones completas para instalar, ejecutar, probar e interpretar el
proyecto están en [project/README.md](project/README.md).

---

