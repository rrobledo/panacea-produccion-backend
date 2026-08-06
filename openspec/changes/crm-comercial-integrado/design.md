## Context

Este backend (`panacea-produccion-backend`) **es** el ERP al que se refiere
el SRS: ya persiste `clientes`, ventas al cliente (`panacea_sales_v2`,
consultada hoy por `analytics_service`/`ventas.py`), compras a proveedores
(`costos_compra`/`compras_compra` — dominio distinto, dinero saliente, sin
relación con el historial de compras de un cliente), pagos, proveedores, y
expone su propia autenticación JWT (`app/auth/`) con un
único enum de roles `user_role` (`admin`, `user`) consumido por
`require_role(*roles)`. El SRS asume una arquitectura de tres sistemas
separados (ERP —API→ CRM ←API— Club de Socios), pero como el CRM se
construye **dentro de este mismo backend**, la mitad de esa integración
(ERP↔CRM) es en realidad un solo proceso con una sola base de datos: no
hace falta una API HTTP entre ambos, sólo separación lógica a nivel de
servicios/tablas. El Club de Socios sí es un sistema externo genuino (no
vive en este repo), así que esa integración sí requiere un cliente HTTP.

El repo ya tiene convenciones establecidas que este change debe seguir:
prefijo de tabla por dominio (`costos_*`, `compras_*`), migraciones SQL
aditivas en `migrations/000N_*.sql` con espejo en
`docker/init-db/0N_*.sql`, capa `models/schemas/services/routers` por
módulo, ledger derivado vía trigger de Postgres para saldos
(`compras_movimiento_cc`), y un router `cron.py` con
`require_cron_secret` para jobs internos recurrentes.

## Goals / Non-Goals

**Goals:**
- Modelar las 8 capabilities nuevas (`crm-contactos`, `crm-campanas`,
  `crm-segmentacion`, `crm-visitas`, `crm-oportunidades`,
  `crm-integracion-erp`, `crm-integracion-club-socios`,
  `crm-dashboards-kpis`) reusando las convenciones ya establecidas en el
  repo en vez de introducir un patrón nuevo.
- Extender el modelo de roles existente de forma aditiva, sin romper el
  uso actual de `admin`/`user` en los routers no-CRM.
- Dejar la integración con el Club de Socios detrás de una interfaz clara,
  aunque el contrato exacto de esa API todavía no esté confirmado.
- Que el CRM nunca sea la fuente de verdad de una venta: siempre lee
  `clientes`/`panacea_sales_v2` vía `erp_cliente_id`↔`customer_id`, nunca
  las duplica ni reescribe (RN-001). Nota (corregida durante la
  implementación): la venta al cliente vive en `panacea_sales_v2` (hecho de
  ventas, ya usado por `analytics_service`/`ventas.py`), **no** en
  `compras_compra` — esa tabla es el libro de compras a proveedores de este
  mismo backend (dinero saliente), un dominio completamente distinto sin
  relación con el historial de compras de un cliente.

**Non-Goals:**
- Automatización de marketing (WhatsApp/Email) — roadmap Fase 4 del SRS,
  sin RF numerado ni modelo de datos; no se diseña acá.
- Multiempresa/franquicias — roadmap Fase 5, mismo motivo.
- Reemplazar o migrar el módulo de compras/pagos/proveedores existente —
  el CRM se suma, no toca ese código.
- Un almacén analítico/OLAP separado para los dashboards — se calculan
  con SQL sobre las tablas operativas, como ya hace
  `produccion_stats.py`/`analytics_service`.

## Decisions

**Prefijo de tablas `crm_*`.** Igual que `costos_*`/`compras_*`, cada
tabla nueva usa el prefijo `crm_`: `crm_contacto`, `crm_empresa`,
`crm_vendedor`, `crm_rubro`, `crm_ciudad`, `crm_origen`, `crm_campana`,
`crm_contacto_campana`, `crm_segmento`, `crm_contacto_segmento`,
`crm_visita`, `crm_etapa_venta`, `crm_oportunidad`, `crm_actividad`,
`crm_club_socio_cache`, `crm_auditoria`. Alternativa descartada: un
schema Postgres separado (`crm.*`) — se descarta por ser el único módulo
del repo que lo haría, rompiendo la convención de "un schema, prefijo por
dominio" que ya usan todos los demás.

**`Contacto.erp_cliente_id` es una FK real, nullable.** Como CRM y ERP
comparten base de datos, no hay razón para tratar el vínculo como una
referencia débil: `crm_contacto.erp_cliente_id` es
`FOREIGN KEY REFERENCES clientes(idcliente)`, nullable (RN-002: un
contacto puede existir sin ERP) y se completa recién en la primera compra
(RN-003). Alternativa descartada: guardar el id como entero suelto sin FK
— se pierde integridad referencial gratis que la misma base ya puede dar.

**`Vendedor` es un perfil CRM ligado a `users`, no una identidad nueva.**
`crm_vendedor` tiene `user_id` FK a `users.id` (nullable sólo mientras se
carga el perfil, luego requerido) en vez de duplicar
nombre/email/credenciales. Evita un segundo sistema de identidad para la
misma persona que ya tiene login en este backend.

**Roles: ampliar el enum `user_role` existente, no crear uno paralelo.**
`ALTER TYPE user_role ADD VALUE 'gerencia' | 'marketing' | 'supervisor_comercial' | 'vendedor'`
(los valores nuevos se agregan a `admin`/`user` ya existentes; no se
renombra ni se quita nada). `require_role(*roles)` no cambia de firma —
sólo los routers del CRM empiezan a pasarle los roles nuevos. Alternativa
descartada: un rol/tabla de permisos separada sólo para CRM — se
descarta porque fragmentaría la autorización en dos sistemas paralelos
sobre el mismo token JWT.

**Segmentación dinámica: definición declarativa + materialización por
cron, no evaluación en cada request.** `crm_segmento.criterio` guarda la
definición del segmento como JSON (filtros sobre atributos de contacto y
agregados de compra); la pertenencia real (`crm_contacto_segmento`) se
recalcula por un job bajo `/internal/cron/crm-recompute-segmentos`
(mismo patrón `require_cron_secret` que `cron.py`) más un endpoint manual
de recompute. Alternativa descartada: JOIN/filtro en vivo en cada
consulta de dashboard — demasiado caro para KPIs como "ventas por
segmento" que ya cruzan `panacea_sales_v2`.

**Cache local de Club de Socios, refrescada por cron.** `crm_club_socio_cache`
guarda el último estado conocido (categoría, puntos, fecha de alta) por
contacto, poblado por un cliente HTTP (`ClubSociosClient`, interfaz nueva
en `app/services/`) contra la API real del Club — el contrato exacto
(endpoint, autenticación, payload) es una pregunta abierta (ver más
abajo). El dashboard de cliente lee siempre de la cache local, nunca hace
la llamada externa en el camino síncrono de una request de usuario.

**Auditoría a nivel de servicio, no trigger de DB.** `crm_auditoria`
(entidad, entidad_id, campo, valor_anterior, valor_nuevo, usuario_id,
fecha) se escribe desde la capa `services`, porque necesita el usuario
autenticado de turno (disponible en el request, no en un trigger SQL).
Distinto del patrón trigger de `compras_movimiento_cc`, que deriva un
saldo puramente a partir de datos ya en la fila — acá el dato "quién lo
hizo" no existe a nivel de tabla sin agregarlo a cada una.

**Dashboards/KPIs: SQL agregado bajo demanda, sin OLAP aparte.** Mismo
patrón que `analytics_service`/`produccion_stats.py`: cada KPI es una
query (o un pequeño set de queries) en un `crm_analytics_service.py`
nuevo, expuesta por router, sin tabla de hechos precalculada. Si el
volumen lo justifica más adelante, se puede materializar — no se hace
ahora (YAGNI).

**No auth por API-key en los routers de escritura del CRM.** Consistente
con el resto del backend (la auth por API-key en escrituras se sacó
deliberadamente de este repo): los routers CRM usan el mismo JWT +
`require_role` que todo lo demás, no un esquema nuevo.

## Risks / Trade-offs

- [Riesgo] El contrato de la API del Club de Socios no está confirmado →
  bloquea la implementación real de `crm-integracion-club-socios`.
  Mitigación: la capability se implementa contra una interfaz
  (`ClubSociosClient`) con una implementación stub/mock desde el día uno;
  la implementación real se conecta cuando el contrato se confirme, sin
  tocar el resto del CRM.
- [Riesgo] `ALTER TYPE user_role ADD VALUE` no puede usarse en la misma
  transacción en la que después se lee/inserta ese valor nuevo (limitación
  de Postgres). Mitigación: migración dedicada y aislada
  (`migrations/000N_crm_roles.sql`) que sólo agrega los valores, separada
  de cualquier migración que ya los use.
- [Riesgo] Nueve capabilities en un solo change es mucho para revisar e
  implementar de una sola pasada. Mitigación: `tasks.md` se organiza en
  grupos independientes por capability (igual que
  `redesign-cuenta-corriente-proveedor`), permitiendo mergear/revisar de a
  partes aunque el proposal cubra el módulo completo.
- [Riesgo] Segmentación materializada por cron puede quedar desactualizada
  entre corridas. Mitigación: `crm_contacto_segmento` guarda
  `recalculado_en`; se expone junto con el resultado para que la UI pueda
  mostrar "actualizado hace X" en vez de asumir tiempo real.
- [Riesgo] Ampliar el enum de roles compartido (`user_role`) es un cambio
  a una tabla (`users`) que usa todo el backend, no sólo el CRM. Mitigación:
  estrictamente aditivo (nunca se quita/renombra un valor existente), y
  `require_role("admin")` sigue funcionando igual en todos los routers no
  tocados por este change.

## Migration Plan

Migraciones aditivas, una por grupo de capability, siguiendo el mismo par
`migrations/000N_*.sql` + `docker/init-db/0N_*.sql` ya usado en el repo,
en este orden de dependencia:

1. `crm_contacto`, `crm_empresa`, `crm_vendedor`, `crm_rubro`, `crm_ciudad`,
   `crm_origen` (capability `crm-contactos`).
2. `crm_campana`, `crm_contacto_campana` (`crm-campanas`).
3. `crm_segmento`, `crm_contacto_segmento` (`crm-segmentacion`).
4. `crm_visita` (`crm-visitas`).
5. `crm_etapa_venta`, `crm_oportunidad`, `crm_actividad`
   (`crm-oportunidades`).
6. `crm_club_socio_cache` (`crm-integracion-club-socios`).
7. `crm_auditoria` (transversal, usada por varias capabilities).
8. `ALTER TYPE user_role ADD VALUE ...` (roles nuevos), migración aislada
   por la limitación de Postgres ya mencionada.

Cada migración es aditiva (no altera ni dropea tablas existentes de
compras/clientes/proveedores) y sigue la convención de dry-run del repo
(`BEGIN;` ... `-f migrations/000N_*.sql` ... `ROLLBACK;` antes de aplicar
con `-1`). No hay rollback automático de datos: al ser todas tablas
nuevas, el rollback es simplemente no aplicar (o `DROP TABLE`) sin
impacto en el resto del sistema.

## Open Questions

- ¿Cuál es el contrato real de la API del Club de Socios (auth, endpoint,
  payload de socio/categoría/puntos)? Bloquea la implementación real de
  `crm-integracion-club-socios` (queda con cliente stub hasta resolverlo).
- ¿"Empresa" necesita su propio `erp_cliente_id`/vínculo a `clientes`
  además del que tiene cada `Contacto` que pertenece a ella, para el caso
  B2B donde el cliente ERP es la empresa y no la persona de contacto?
- ¿Quién define/edita los `Segmento` (criterios JSON) — Marketing vía
  UI, o se cargan a mano por ahora? Afecta si `crm-segmentacion` necesita
  un editor de criterios en esta fase o alcanza con crearlos por API/SQL.
- ¿Los `Rubro`/`Ciudad`/`Origen` son catálogos fijos a sembrar una vez, o
  necesitan CRUD propio desde el día uno?
