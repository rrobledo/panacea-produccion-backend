def calcular_liquidacion(sueldo_bruto: float, descuento_sindical: float = 0.0, alicuota_art: float = 5.0) -> dict:
    descuento_jubilacion = sueldo_bruto * 0.11
    descuento_obra_social = sueldo_bruto * 0.03
    descuento_pami = sueldo_bruto * 0.03
    descuento_sindicato = sueldo_bruto * (descuento_sindical / 100)

    total_descuentos = descuento_jubilacion + descuento_obra_social + descuento_pami + descuento_sindicato
    sueldo_neto = sueldo_bruto - total_descuentos

    contrib_jubilacion = sueldo_bruto * 0.1077
    contrib_obra_social = sueldo_bruto * 0.06
    contrib_pami = sueldo_bruto * 0.015
    contrib_asignaciones = sueldo_bruto * 0.0444
    contrib_fondo_empleo = sueldo_bruto * 0.0111
    contrib_art = sueldo_bruto * (alicuota_art / 100)

    total_cargas_patronales = (
        contrib_jubilacion + contrib_obra_social + contrib_pami + contrib_asignaciones + contrib_fondo_empleo + contrib_art
    )

    costo_total_empresa = sueldo_bruto + total_cargas_patronales

    return {
        "sueldo_bruto": sueldo_bruto,
        "descuento_jubilacion": descuento_jubilacion,
        "descuento_obra_social": descuento_obra_social,
        "descuento_pami": descuento_pami,
        "descuento_sindicato": descuento_sindicato,
        "total_descuentos": total_descuentos,
        "sueldo_neto": sueldo_neto,
        "contrib_jubilacion": contrib_jubilacion,
        "contrib_obra_social": contrib_obra_social,
        "contrib_pami": contrib_pami,
        "contrib_asignaciones": contrib_asignaciones,
        "contrib_fondo_empleo": contrib_fondo_empleo,
        "contrib_art": contrib_art,
        "total_cargas_patronales": total_cargas_patronales,
        "costo_total_empresa": costo_total_empresa,
        "costo_hora": costo_total_empresa / (44 * 5),
    }
