## ADDED Requirements

### Requirement: Registro de visita
The system SHALL persist a `Visita` entity associated with a `Contacto`
and a `Vendedor`, recording `fecha`, `notas`, and an optional result.

#### Scenario: Alta de visita
- **WHEN** se crea una `Visita` con `contacto_id`, `vendedor_id` y
  `fecha` válidos
- **THEN** la visita queda persistida asociada a ese contacto y vendedor

#### Scenario: Alta de visita con contacto o vendedor inexistente es rechazada
- **WHEN** se intenta crear una `Visita` con `contacto_id` o
  `vendedor_id` que no existen
- **THEN** el sistema rechaza la operación con un error de referencia
  inválida

### Requirement: Visita puede originar una oportunidad
The system SHALL allow a `Visita` to be the origin of an `Oportunidad`,
recording the link from the opportunity back to the visit that created it.

#### Scenario: Crear oportunidad desde una visita
- **WHEN** se crea una `Oportunidad` indicando una `Visita` de origen
- **THEN** la `Oportunidad` queda persistida con la referencia a esa
  `Visita`

#### Scenario: Visita sin oportunidad asociada sigue siendo válida
- **WHEN** una `Visita` no genera ninguna `Oportunidad`
- **THEN** la `Visita` sigue existiendo y siendo consultable normalmente

### Requirement: Auditoría de cambios sobre visita
The system SHALL record every create/update of a `Visita` in an audit log
entry with the changed entity, field, previous value, new value, acting
user, and timestamp (RN-005).

#### Scenario: Alta de visita queda auditada
- **WHEN** se crea una `Visita`
- **THEN** se crea una entrada de auditoría registrando el usuario que la
  creó y la fecha

### Requirement: Adjuntos de audio, video o imagen sobre una visita
The system SHALL allow uploading audio, video, or image files attached to a
`Visita`, for later analysis, storing the file content directly in Postgres
(same pattern as `compras_compra_adjunto`/`compras_pago_adjunto`) rather
than an external object store. Non audio/video/image content types SHALL be
rejected, and files over 4MB SHALL be rejected with a clear error instead
of relying on the platform's opaque request-size limit.

#### Scenario: Subir un adjunto de imagen
- **WHEN** se sube un archivo `image/*` a una `Visita` existente
- **THEN** el archivo queda guardado y aparece en el listado de adjuntos
  de esa visita

#### Scenario: Subir un adjunto de audio o video
- **WHEN** se sube un archivo `audio/*` o `video/*` a una `Visita`
  existente
- **THEN** el archivo queda guardado igual que un adjunto de imagen

#### Scenario: Tipo de archivo no soportado es rechazado
- **WHEN** se intenta subir un archivo que no es audio, video ni imagen
  (por ejemplo un PDF)
- **THEN** el sistema rechaza la operación con un error 400

#### Scenario: Archivo más grande que el límite es rechazado
- **WHEN** se intenta subir un archivo de más de 4MB
- **THEN** el sistema rechaza la operación con un error claro en vez de
  dejar que la plataforma corte la request

#### Scenario: Descargar un adjunto inexistente
- **WHEN** se pide un adjunto que no existe (o no pertenece a esa visita)
- **THEN** el sistema responde 404
