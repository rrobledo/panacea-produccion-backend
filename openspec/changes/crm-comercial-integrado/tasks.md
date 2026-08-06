## 1. Fundación transversal: roles y auditoría

- [x] 1.1 Migración `migrations/000N_crm_roles.sql` (+ espejo en
      `docker/init-db/`) que agrega `gerencia`, `marketing`,
      `supervisor_comercial`, `vendedor` a `user_role` vía
      `ALTER TYPE ... ADD VALUE`, aislada de cualquier otra migración.
- [x] 1.2 Actualizar `app/models/user.py` (`UserRole = Enum(...)`) para
      incluir los roles nuevos.
- [x] 1.3 Migración `crm_auditoria` (`entidad`, `entidad_id`, `campo`,
      `valor_anterior`, `valor_nuevo`, `usuario_id`, `fecha`) + espejo
      `docker/init-db/`.
- [x] 1.4 `app/models/crm_auditoria.py` y un helper de servicio
      (`app/services/crm_auditoria_service.py`) para escribir entradas de
      auditoría desde cualquier service del CRM.
- [x] 1.5 Tests: nuevos roles aceptados por `require_role`, migración de
      roles no rompe usuarios/roles existentes, helper de auditoría
      persiste una entrada correctamente.

## 2. Contactos, empresas y catálogos (`crm-contactos`)

- [x] 2.1 Migración `crm_rubro`, `crm_ciudad`, `crm_origen`, `crm_empresa`,
      `crm_vendedor` (con `user_id` FK nullable a `users.id`),
      `crm_contacto` (con `erp_cliente_id` FK nullable a
      `clientes.idcliente`, `empresa_id`, `rubro_id`, `ciudad_id`,
      `origen_id` nullable) + espejo `docker/init-db/`.
- [x] 2.2 Modelos SQLAlchemy: `app/models/crm_contacto.py`,
      `crm_empresa.py`, `crm_vendedor.py`, `crm_rubro.py`, `crm_ciudad.py`,
      `crm_origen.py`.
- [x] 2.3 Schemas Pydantic (`app/schemas/crm_contacto.py`, etc.):
      Create/Update/Read para cada entidad.
- [x] 2.4 `app/services/crm_contacto_service.py` (+ `crm_empresa_service.py`,
      `crm_catalogos_service.py`): CRUD con validación de referencias
      (rubro/ciudad/origen/empresa/erp_cliente_id existentes) y
      escritura de auditoría en updates.
- [x] 2.5 `app/routers/crm_contactos.py` (+ router de empresas/catálogos):
      endpoints CRUD gateados por rol comercial, registrados en
      `app/main.py`.
- [x] 2.6 Tests unitarios: alta sin ERP, alta B2B con empresa, rechazo de
      referencias inexistentes, listado de contactos por empresa,
      auditoría de edición.

## 3. Campañas (`crm-campanas`)

- [x] 3.1 Migración `crm_campana`, `crm_contacto_campana` (constraint de
      unicidad `contacto_id`+`campana_id`) + espejo `docker/init-db/`.
- [x] 3.2 Modelo, schema, service (`crm_campana_service.py`, incluye
      asociación idempotente y conteo de conversión), router
      `crm_campanas.py` registrado en `app/main.py`.
- [x] 3.3 Tests: alta de campaña abierta/cerrada, asociación duplicada no
      crea fila extra, conteo de contactos con ERP vinculado por campaña.

## 4. Segmentación (`crm-segmentacion`)

- [x] 4.1 Migración `crm_segmento` (`criterio` como `jsonb`),
      `crm_contacto_segmento` (con `recalculado_en`) + espejo
      `docker/init-db/`.
- [x] 4.2 Modelo, schema, `crm_segmentacion_service.py` con evaluación de
      `criterio` contra contacto+compras ERP y recompute (agregar/quitar
      filas `crm_contacto_segmento`).
      Nota: la evaluación implementada filtra sobre atributos directos de
      Contacto (tipo/empresa/rubro/ciudad/origen); agregados de compra ERP
      (frecuencia/inactividad) se calculan en `crm-dashboards-kpis`
      (grupo 9), no como criterio de segmento — mantiene el filtro simple
      y evita duplicar esa lógica en dos lugares.
- [x] 4.3 Endpoint interno `/internal/cron/crm-recompute-segmentos`
      (patrón `require_cron_secret` de `app/routers/cron.py`) + endpoint
      manual autenticado de recompute bajo `crm_segmentacion.py`.
- [x] 4.4 Tests: recompute agrega y remueve membresía según criterio,
      recompute manual respeta `require_role`, timestamp de recálculo se
      actualiza.

## 5. Visitas (`crm-visitas`)

- [x] 5.1 Migración `crm_visita` (`contacto_id`, `vendedor_id`, `fecha`,
      `notas`, resultado opcional) + espejo `docker/init-db/`.
- [x] 5.2 Modelo, schema, `crm_visita_service.py` (con auditoría), router
      `crm_visitas.py` registrado en `app/main.py`.
      Nota: tarea 2.x no incluyó CRUD de `Vendedor` (solo modelo); se
      completó acá (`crm_vendedor_service.py` + endpoints en
      `crm_contactos.py`) porque `crm_visita.vendedor_id` lo necesita para
      ser usable end-to-end.
- [x] 5.3 Tests: alta de visita, rechazo por contacto/vendedor
      inexistente, auditoría de alta.

## 6. Oportunidades (`crm-oportunidades`)

- [x] 6.1 Migración `crm_etapa_venta` (catálogo ordenado de etapas:
      Lead, Visita, Interesado, Muestras, Presupuesto, Negociación,
      Primera Compra, Cliente Activo), `crm_oportunidad` (`contacto_id`,
      `visita_id` nullable de origen, `etapa_id`), `crm_actividad`
      (`oportunidad_id`, `tipo`, `fecha`, `notas`) + espejo
      `docker/init-db/`.
- [x] 6.2 Modelos, schemas, `crm_oportunidad_service.py` (transición de
      etapa con validación de "Primera Compra" solo si hay compra ERP,
      auditoría de cambios de etapa; incluye `add_actividad`/
      `list_actividades`, no se separó un `crm_actividad_service.py`
      aparte — Actividad no tiene ciclo de vida propio fuera de su
      Oportunidad).
      Corrección importante encontrada acá: la "compra ERP" que valida el
      pase a "Primera Compra" es `panacea_sales_v2` (ventas al cliente,
      join por `customer_id`/`erp_cliente_id`) — **no**
      `compras_compra`, que es el libro de compras a proveedores de este
      mismo backend, un dominio no relacionado. `design.md` y el spec de
      `crm-integracion-erp` tenían esa referencia incorrecta y se
      corrigieron.
- [x] 6.3 Routers `crm_oportunidades.py` (incluye alta de oportunidad
      desde una visita) registrados en `app/main.py`.
- [x] 6.4 Tests: alta en etapa Lead por defecto, cambio de etapa,
      creación desde visita, rechazo de "Primera Compra" sin ERP
      vinculado, actividades ordenadas por fecha, auditoría de cambio de
      etapa.

## 7. Integración ERP (`crm-integracion-erp`)

- [x] 7.1 `app/services/crm_erp_integration_service.py`: vínculo manual
      contacto↔`clientes` (validando existencia), reconciliación por
      email para autovinculación (`autovincular_por_email` — pasada
      periódica/manual, no hay evento de "nueva venta" que este backend
      pueda enganchar porque `panacea_sales_v2` es poblada externamente),
      consulta de historial de compras y top productos por
      `erp_cliente_id` (joins de solo lectura sobre `clientes`/
      `panacea_sales_v2` — no `compras_compra`, ver nota en 6.2 —, sin
      escritura).
- [x] 7.2 Endpoints bajo `crm_contactos.py`: vínculo manual
      (`PUT .../erp-cliente`), autovinculación (`POST .../autovincular-erp`),
      historial de compras y productos más consumidos de un contacto.
- [x] 7.3 Tests: vínculo manual válido/inválido, autovinculación por
      email con compra ERP existente, historial vacío sin ERP, top
      productos ordenado por consumo, y un test que recorre los routers
      del CRM verificando que ninguno expone escritura sobre
      `/clientes`/`/sales*`.

## 8. Integración Club de Socios (`crm-integracion-club-socios`)

- [x] 8.1 Migración `crm_club_socio_cache` (`contacto_id`, `socio_id`,
      `categoria`, `puntos`, `fecha_alta`, `actualizado_en`) + espejo
      `docker/init-db/`.
- [x] 8.2 `app/services/club_socios_client.py`: interfaz `ClubSociosClient`
      + implementación stub (contrato real pendiente, ver Open Questions
      de `design.md`).
- [x] 8.3 `app/services/crm_club_socio_service.py`: lectura desde cache
      local, `link_socio` (vincula/actualiza `socio_id` de un contacto),
      job de refresco (`/internal/cron/crm-refresh-club-socios` con
      `require_cron_secret`) que llama al cliente y actualiza cache.
- [x] 8.4 Tests: lectura de cache existe/ausente, refresco actualiza
      valores, consulta no falla si el cliente externo lanza error
      (usa último valor cacheado).

## 9. Dashboards y KPIs (`crm-dashboards-kpis`)

- [x] 9.1 `app/services/crm_analytics_service.py`: queries de conversión
      (visitas→clientes, ROI de campaña vía `crm_campana_service.
      get_conversion`), CAC, CLV/ticket promedio/frecuencia/última compra
      (`valor_cliente`), ventas por segmento/ciudad/vendedor,
      inactivos.
      Dos decisiones nuevas no cubiertas por `design.md` original,
      necesarias para que CAC/ROI fueran calculables de verdad en vez de
      quedar como stub: se agregó `crm_campana.costo` (numeric nullable)
      y `crm_contacto.observaciones` (text nullable) vía migración
      `0017_crm_dashboards_kpis_support.sql`. "Ventas por vendedor" se
      atribuye por la última `Visita` de cada contacto (no hay un
      "vendedor asignado" persistente en el modelo — no estaba en el
      spec original tampoco).
- [x] 9.2 `app/routers/crm_dashboards.py`: dashboard ejecutivo
      (admin/gerencia), dashboard de vendedor (auto-scoped: un usuario
      con rol `vendedor` sólo puede ver el dashboard del `CrmVendedor`
      ligado a su `user_id`; supervisor_comercial/gerencia/admin ven
      cualquiera), dashboard de marketing, dashboard 360° de contacto —
      todos gateados por rol, registrados en `app/main.py`.
- [x] 9.3 Exportación CSV genérica (`_csv_response`, StreamingResponse)
      aplicada a los reportes de ventas-por-segmento y clientes-inactivos
      (`?formato=csv`).
- [x] 9.4 Tests: KPIs con datos mínimos de fixture (ventas en
      `panacea_sales_v2`), vendedor no puede ver dashboard ajeno,
      dashboard 360° con y sin vínculo ERP, exportación CSV.

## 10. Documentación y validación final

- [x] 10.1 Actualizar `README.md` con los endpoints nuevos del CRM (nueva
      sección "CRM (crm-comercial-integrado)"). No se agregó ninguna
      variable de entorno nueva — `ClubSociosClient` es un stub sin
      credenciales todavía (contrato pendiente, ver Open Questions de
      `design.md`).
- [x] 10.2 `pytest tests/unit -q` en verde con toda la suite: 223 passed
      (165 baseline + 58 nuevos de este change), verificado dos veces —
      contra la DB de test existente y contra una recreada desde cero
      (`docker compose down -v && up -d`) para confirmar que
      `docker/init-db/13..21_*.sql` aplican limpio en orden y en paridad
      con `migrations/0009..0017_*.sql`.
- [x] 10.3 `openspec validate crm-comercial-integrado --type change --strict`
      en verde.
