-- El código de una Orden de Producción tiene que ser único.
--
-- Hasta ahora la unicidad la garantizaba de rebote la guarda que impedía
-- generar dos veces la misma fecha: la numeración `AAMMDD-NN` arrancaba en 01
-- en cada generación y nunca había una segunda. Al permitir completar un día
-- ya generado, esa numeración pasa a continuar desde el máximo del día — y
-- este índice es la red que hace que un error de cálculo falle en el acto en
-- vez de crear dos órdenes con el mismo código en silencio.
--
-- Además el borrado de órdenes elimina sus movimientos de RESERVA buscándolos
-- por `referencia = codigo`: sin unicidad, un código repetido haría que ese
-- borrado se llevara puestas las reservas de otra orden.

CREATE UNIQUE INDEX IF NOT EXISTS ordenes_produccion_codigo_key
    ON ordenes_produccion (codigo);
