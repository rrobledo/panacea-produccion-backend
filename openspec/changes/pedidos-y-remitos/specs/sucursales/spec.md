## ADDED Requirements

### Requirement: Catálogo de sucursales
El sistema SHALL exponer un catálogo de `Sucursal` con `id`, `nombre`
(obligatorio), `tipo` (`SUCURSAL` o `FABRICA`, obligatorio) y `activa`
(booleano, default `true`). El catálogo SHALL soportar creación,
listado y actualización (nombre, tipo, activa) vía
`POST /sucursales`, `GET /sucursales` y `PUT /sucursales/{id}`.

#### Scenario: Crear una sucursal
- **WHEN** un caller envía `POST /sucursales` con
  `{"nombre": "Sucursal Centro", "tipo": "SUCURSAL"}`
- **THEN** la respuesta es 201 con la sucursal creada, `activa=true`

#### Scenario: Crear la fábrica
- **WHEN** un caller envía `POST /sucursales` con
  `{"nombre": "Fábrica", "tipo": "FABRICA"}`
- **THEN** la respuesta es 201 con la sucursal creada

#### Scenario: Tipo inválido es rechazado
- **WHEN** un caller envía `POST /sucursales` con `tipo` fuera de
  `{"SUCURSAL", "FABRICA"}`
- **THEN** la respuesta es 422 y no se crea ninguna sucursal

### Requirement: Listado filtrable de sucursales
El sistema SHALL permitir listar sucursales filtrando por `tipo` y por
`activa`, para poblar los selectores de origen/destino al crear un
remito de transferencia.

#### Scenario: Filtrar solo sucursales activas de tipo SUCURSAL
- **WHEN** un caller envía `GET /sucursales?tipo=SUCURSAL&activa=true`
- **THEN** la respuesta incluye únicamente sucursales con
  `tipo=SUCURSAL` y `activa=true`

### Requirement: Desactivar una sucursal no borra su historial
El sistema SHALL permitir marcar una sucursal como `activa=false` sin
eliminarla, preservando la integridad referencial de los remitos de
transferencia que ya la usaron como origen o destino.

#### Scenario: Desactivar una sucursal con remitos asociados
- **WHEN** un caller envía `PUT /sucursales/{id}` con `{"activa":
  false}` sobre una sucursal usada como `origen_sucursal_id` en algún
  remito existente
- **THEN** la respuesta es 200, la sucursal queda `activa=false` y los
  remitos que la referencian no se modifican
