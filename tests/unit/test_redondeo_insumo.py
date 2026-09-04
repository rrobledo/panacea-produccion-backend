import pytest

from app.services.ordenes_produccion_service import _redondear_insumo


@pytest.mark.parametrize(
    "exacto, esperado",
    [
        (1348.6666666666667, 1349),  # decimales largos del escalado de receta
        (0.4, 1),                    # piso: >0 nunca cae a 0 (design.md Decision 4)
        (0.0001, 1),
        (0.0, 0),                    # insumo no requerido: se omite
        (2.5, 3),                    # half-up, no banker's rounding (round(2.5) da 2)
        (1.5, 2),                    # half-up, no banker's rounding (round(1.5) da 2 por casualidad)
        (3.5, 4),                    # half-up (round(3.5) da 4)
        (4.5, 5),                    # half-up (round(4.5) da 4)
        (50.0, 50),                  # entero exacto queda igual
        (149.4, 149),
    ],
)
def test_redondear_insumo(exacto, esperado):
    assert _redondear_insumo(exacto) == esperado


def test_redondear_insumo_no_usa_banker_rounding():
    """Si esto falla es porque se cambió Decimal/ROUND_HALF_UP por round()."""
    casos = [2.5, 4.5, 0.5]
    assert [_redondear_insumo(c) for c in casos] == [3, 5, 1]
    assert [round(c) for c in casos] == [2, 4, 0]
