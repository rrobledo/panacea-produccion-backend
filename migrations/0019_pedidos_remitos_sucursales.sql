-- pedidos-y-remitos: introduces Pedido (customer order) and a redesigned
-- Remito (dispatch/transfer document) as separate entities, plus a new
-- Sucursal catalog for inter-branch/factory transfer remitos. See
-- openspec/changes/pedidos-y-remitos/design.md.
--
-- costos_remitos/costos_remitodetalles are NOT touched by this migration —
-- they remain as read-only historical archive, the source that
-- scripts/migrate_remitos_to_pedidos_remitos.sql reads from. This
-- migration is purely additive.
--
-- Idempotent: safe to re-run. Intended usage:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "BEGIN;" -f migrations/0019_pedidos_remitos_sucursales.sql -c "ROLLBACK;"   -- dry run
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f migrations/0019_pedidos_remitos_sucursales.sql                          -- apply for real

CREATE TABLE IF NOT EXISTS sucursales_sucursal (
    id      BIGSERIAL PRIMARY KEY,
    nombre  VARCHAR(255) NOT NULL,
    tipo    VARCHAR(20) NOT NULL,
    activa  BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS pedidos_pedido (
    id             BIGSERIAL PRIMARY KEY,
    cliente_id     INTEGER REFERENCES clientes(idcliente),
    vendedor       VARCHAR(255) NOT NULL,
    estado         VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    fecha_carga    TIMESTAMPTZ NOT NULL,
    fecha_entrega  TIMESTAMPTZ NOT NULL,
    observaciones  VARCHAR(1000)
);

CREATE INDEX IF NOT EXISTS pedidos_pedido_cliente_id_idx ON pedidos_pedido (cliente_id);
CREATE INDEX IF NOT EXISTS pedidos_pedido_estado_idx ON pedidos_pedido (estado);

CREATE TABLE IF NOT EXISTS pedidos_pedido_detalle (
    id                  BIGSERIAL PRIMARY KEY,
    pedido_id           BIGINT NOT NULL REFERENCES pedidos_pedido(id) ON DELETE CASCADE,
    producto_id         INTEGER NOT NULL REFERENCES costos_productos(id),
    cantidad_pedida     INTEGER NOT NULL,
    cantidad_entregada  INTEGER NOT NULL DEFAULT 0,
    -- How much of cantidad_entregada has already been copied onto a
    -- generated Remito (see design.md Decision 3): a transition to
    -- LISTO_PARA_ENTREGA/ENTREGADO only remitos the delta
    -- (cantidad_entregada - cantidad_remitida), then this catches up to
    -- cantidad_entregada.
    cantidad_remitida   INTEGER NOT NULL DEFAULT 0,
    observaciones       VARCHAR(1000)
);

CREATE INDEX IF NOT EXISTS pedidos_pedido_detalle_pedido_id_idx ON pedidos_pedido_detalle (pedido_id);

-- Remito (rediseñado): tipo=VENTA (cliente_id + pedido_id opcional) o
-- tipo=TRANSFERENCIA (origen/destino sucursal, sin cliente/pedido). La
-- combinación de campos condicionales se valida a nivel Pydantic
-- (app/schemas/remito.py), no acá — mismo criterio que CompraDetalle.tipo.
CREATE TABLE IF NOT EXISTS remitos_remito (
    id                  BIGSERIAL PRIMARY KEY,
    tipo                VARCHAR(20) NOT NULL,
    cliente_id          INTEGER REFERENCES clientes(idcliente),
    pedido_id           BIGINT REFERENCES pedidos_pedido(id),
    origen_sucursal_id  BIGINT REFERENCES sucursales_sucursal(id),
    destino_sucursal_id BIGINT REFERENCES sucursales_sucursal(id),
    vendedor            VARCHAR(255),
    observaciones       VARCHAR(1000),
    fecha_carga         TIMESTAMPTZ NOT NULL,
    fecha_preparacion   TIMESTAMPTZ,
    fecha_listo         TIMESTAMPTZ,
    fecha_despacho      TIMESTAMPTZ,
    fecha_recibido      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS remitos_remito_cliente_id_idx ON remitos_remito (cliente_id);
CREATE INDEX IF NOT EXISTS remitos_remito_pedido_id_idx ON remitos_remito (pedido_id);
CREATE INDEX IF NOT EXISTS remitos_remito_tipo_idx ON remitos_remito (tipo);

CREATE TABLE IF NOT EXISTS remitos_remito_detalle (
    id             BIGSERIAL PRIMARY KEY,
    remito_id      BIGINT NOT NULL REFERENCES remitos_remito(id) ON DELETE CASCADE,
    producto_id    INTEGER NOT NULL REFERENCES costos_productos(id),
    cantidad       INTEGER NOT NULL,
    observaciones  VARCHAR(1000)
);

CREATE INDEX IF NOT EXISTS remitos_remito_detalle_remito_id_idx ON remitos_remito_detalle (remito_id);
