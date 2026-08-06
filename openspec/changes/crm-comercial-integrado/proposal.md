## Why

Hoy la gestión comercial (contactos, visitas, campañas, oportunidades) vive
fuera de cualquier sistema — planillas sueltas o memoria de cada vendedor —
mientras el ERP (este repo) es la única fuente de verdad de clientes,
compras y facturación, y el Club de Socios administra la fidelización por
separado. No existe una vista 360° del cliente que cruce origen comercial,
interacciones y compras reales, ni forma de medir conversión de campañas,
CAC/CLV o inactividad de clientes. Este change introduce un módulo de CRM
que centraliza esa gestión comercial B2B/B2C y consulta (sin duplicar) las
ventas del ERP y los puntos/categoría del Club de Socios.

## What Changes

- Nuevas entidades CRM: `Contacto`, `Empresa`, `Vendedor`, `Rubro`, `Ciudad`,
  `Origen` — alta y gestión de contactos B2B/B2C, con vínculo opcional a
  `erp_cliente_id` (tabla `clientes` existente) y a socio del Club.
- Gestión de campañas: `Campaña`, `Contacto_Campaña` — asociar contactos a
  campañas, medir conversión campaña→registro→primera compra.
- Segmentación dinámica: `Segmento`, `Contacto_Segmento` — segmentos
  calculados sobre atributos de contacto/compra (ciudad, rubro, frecuencia,
  inactividad).
- Registro de visitas: `Visita` (B2B), con capacidad de originar una
  `Oportunidad`.
- Pipeline comercial: `Oportunidad`, `Etapa_Venta`, `Actividad` — flujo
  Lead→Visita→Interesado→Muestras→Presupuesto→Negociación→Primera Compra.
- Integración de solo lectura con el ERP: importación/vínculo de clientes
  existentes vía `erp_cliente_id`, consulta de historial de compras,
  productos más consumidos y facturación de los últimos 12 meses — el ERP
  sigue siendo la única fuente de ventas, el CRM nunca las duplica ni
  reescribe.
- Integración de solo lectura con el Club de Socios: `Club_Socio` (estado,
  categoría, puntos) asociado al contacto.
- Dashboards y KPIs: dashboard ejecutivo, de vendedor y de marketing;
  conversión visitas→clientes, conversión campaña→registro→primera compra,
  ROI por campaña, CAC, CLV, ticket promedio, frecuencia de compra, clientes
  inactivos/recuperados, ventas por segmento/ciudad/vendedor; exportación de
  reportes; alertas de clientes inactivos.
- **BREAKING** (potencial): extensión del modelo de roles existente
  (`user`/`admin` en `role-authorization`/`user-identity`) a un esquema más
  granular (Administrador, Gerencia, Marketing, Supervisor Comercial,
  Vendedor) para gatear los endpoints del CRM — ver `design.md` para cómo
  se preserva compatibilidad con los roles actuales.
- Auditoría: toda alta/edición de contacto, visita, oportunidad y actividad
  queda registrada (quién, cuándo, qué cambió).

Explícitamente fuera de alcance de este change (mencionado en el SRS como
roadmap Fase 4/5 pero sin modelo de datos ni requisito funcional
numerado): automatización de marketing vía WhatsApp/Email, y soporte
multiempresa/franquicias. El diseño no debe bloquear agregarlos después,
pero no se construyen ahora.

## Capabilities

### New Capabilities
- `crm-contactos`: alta, edición y consulta de `Contacto` (B2B/B2C) y
  `Empresa`, con vínculo opcional a `erp_cliente_id` y a `Club_Socio`;
  catálogos `Rubro`/`Ciudad`/`Origen`.
- `crm-campanas`: gestión de `Campaña` y asociación de contactos a
  campañas (`Contacto_Campaña`), con métricas de conversión.
- `crm-segmentacion`: definición de `Segmento` y evaluación dinámica de
  membresía de contactos (`Contacto_Segmento`).
- `crm-visitas`: registro de `Visita` y su posible conversión en
  `Oportunidad`.
- `crm-oportunidades`: pipeline de `Oportunidad` sobre `Etapa_Venta`, con
  `Actividad` asociadas.
- `crm-integracion-erp`: consulta read-only de clientes/compras/productos
  del ERP desde el CRM vía `erp_cliente_id`, sin duplicar ventas.
- `crm-integracion-club-socios`: consulta read-only de `Club_Socio`
  (estado, categoría, puntos) asociado a un contacto.
- `crm-dashboards-kpis`: dashboards ejecutivo/vendedor/marketing, cálculo
  de KPIs comerciales, alertas de inactividad y exportación de reportes.

### Modified Capabilities
- `role-authorization`: `require_role` debe reconocer los nuevos roles
  comerciales (Administrador, Gerencia, Marketing, Supervisor Comercial,
  Vendedor) además de los existentes (`admin`, `user`), para gatear los
  endpoints del CRM por rol.
- `user-identity`: el enum `role` de la tabla `users` se amplía para incluir
  los roles comerciales nuevos.

## Impact

- **Nuevo código**: modelos/schemas/services/routers bajo `app/models`,
  `app/schemas`, `app/services`, `app/routers` para cada capability nueva
  (patrón ya usado por `compras`, `pagos`, `proveedores`, etc. en este
  repo); nuevas migraciones SQL en `migrations/` + su espejo en
  `docker/init-db/` (convención ya establecida en el repo).
- **Tablas existentes consultadas, no modificadas**: `clientes` (para
  `erp_cliente_id`), y lo que exponga la integración del Club de Socios
  (sistema externo, contrato de API a definir en `design.md`).
- **Tablas existentes modificadas**: `users.role` (ampliación de enum) y el
  dependency `require_role` en `app/auth/` — cambio aditivo pensado para no
  romper el uso actual de `admin`/`user` en el resto del ERP.
- **Dependencias nuevas**: ninguna prevista fuera de lo que ya usa el repo
  (FastAPI/SQLAlchemy/Postgres); la integración con el Club de Socios
  depende de que ese sistema exponga una API o vista consultable (a
  confirmar en `design.md`).
- **Fuera de impacto**: el módulo de costos/compras/pagos/proveedores
  existente no cambia de comportamiento; el CRM es un módulo nuevo que se
  suma al mismo backend.
