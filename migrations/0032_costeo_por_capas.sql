-- masa-procesos-y-maquinaria F6 (tarea 7.1): centro de trabajo con tarifa.
--
-- `responsable` era un enum de cuatro valores que hacía de área, de persona y
-- de criterio de agrupación al mismo tiempo. Pasa a ser una entidad con tarifa
-- horaria y capacidad de turno, que es lo que faltaba para que el costo de mano
-- de obra tenga una fuente: hoy `costo_unitario_mo` aparece en
-- /costos/precio_productos sin ningún dato que lo alimente (design.md D14).
--
-- El enum sigue existiendo en `ordenes_produccion.responsable` y en
-- `costos_programacion.responsable`: el centro de trabajo se referencia por
-- nombre, no por FK, para no tener que migrar esas dos columnas ahora.
--
-- Idempotente: seguro de re-ejecutar.

CREATE TABLE IF NOT EXISTS costos_centro_trabajo (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL,
    tarifa_hora DOUBLE PRECISION NOT NULL DEFAULT 0,
    horas_turno DOUBLE PRECISION NOT NULL DEFAULT 6,
    habilitado BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX IF NOT EXISTS costos_centro_trabajo_nombre_key ON costos_centro_trabajo (nombre);

-- Semilla con los cuatro valores del enum actual, con tarifa en cero: quién
-- carga las tarifas y con qué frecuencia se revisan es una pregunta abierta del
-- design, y poner un número inventado sería peor que dejarlo vacío.
INSERT INTO costos_centro_trabajo (nombre, tarifa_hora, horas_turno)
SELECT nombre, 0, 6
  FROM (VALUES ('Panaderia'), ('Pasteleria'), ('Pastas'), ('Galletas')) AS v(nombre)
 WHERE NOT EXISTS (SELECT 1 FROM costos_centro_trabajo c WHERE c.nombre = v.nombre);
