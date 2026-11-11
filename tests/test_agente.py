import datetime as dt
from email.message import EmailMessage

import pytest

from vuelos import agente, fuente, store
from vuelos.fuente import Oferta

CFG = {"origenes": ["GDL", "QRO"], "destinos": ["MAD"], "pasajeros": 4, "moneda": "mxn",
       "fechas": {"salida": dt.date(2027, 6, 11), "regreso": dt.date(2027, 6, 27)},
       "ciudades": {"GDL": ["Guadalajara"], "QRO": ["Querétaro", "Queretaro"], "MAD": ["Madrid"]},
       "precio_del_correo": "total", "precio_maximo_por_persona": None, "bajada_minima_pct": 3}


def oferta(precio, origen="GDL", msg_id=""):
    return Oferta(origen, "MAD", dt.date(2027, 6, 11), dt.date(2027, 6, 27), precio, "", None,
                  "https://www.google.com/travel/flights", msg_id or f"<{origen}-{precio}@google.com>")


def correo(asunto, cuerpo_html, msg_id="<1@google.com>"):
    m = EmailMessage()
    m["Subject"], m["From"], m["Message-ID"] = asunto, "Google Flights <noreply-travel@google.com>", msg_id
    m.set_content(cuerpo_html, subtype="html")
    return m


@pytest.fixture
def con(tmp_path):
    return store.conectar(tmp_path / "p.sqlite")


def test_es_bajada():
    assert agente.es_bajada(20000, None, CFG)              # primera vez
    assert agente.es_bajada(19000, 20000, CFG)             # -5 %
    assert not agente.es_bajada(19800, 20000, CFG)         # -1 %: ruido
    assert not agente.es_bajada(21000, 20000, CFG)
    assert not agente.es_bajada(20000, None, {**CFG, "precio_maximo_por_persona": 15000})


def test_parse_alerta_en_espanol():
    m = correo("Bajó el precio de tu vuelo a Madrid",
               '<p>Guadalajara a Madrid</p><p>vie, 11 jun – dom, 27 jun · 4 pasajeros</p>'
               '<p><s>MX$120,000</s> <b>MX$100,000</b></p>'
               '<a href="https://www.google.com/travel/flights?tfs=abc&amp;hl=es">Ver vuelos</a>')
    [o] = fuente.parse_message(m, CFG)
    assert (o.origen, o.destino, o.precio) == ("GDL", "MAD", 25000)          # total ÷ 4, el más bajo
    assert o.enlace == "https://www.google.com/travel/flights?tfs=abc&hl=es"
    assert o.msg_id == "<1@google.com>" and o.salida == dt.date(2027, 6, 11)


def test_parse_alerta_en_ingles_por_persona():
    m = correo("Prices dropped for your trip", "<p>Queretaro to Madrid</p><p>$27,500 MXN</p>")
    [o] = fuente.parse_message(m, {**CFG, "precio_del_correo": "por_persona"})
    assert o.origen == "QRO" and o.precio == 27500


def test_parse_ignora_otros_correos():
    assert fuente.parse_message(correo("Tu recibo", "<p>Total $1,500 MXN</p>"), CFG) == []
    assert fuente.parse_message(correo("Vuelo a Lima", "<p>Guadalajara a Lima MX$9,000</p>"), CFG) == []


def test_revisar_guarda_historico_y_avisa_solo_bajadas(con):
    enviados = []
    avisar = lambda t: enviados.append(t) or True
    alertas = [oferta(25000, "GDL"), oferta(30000, "QRO")]
    assert len(agente.revisar(CFG, con, lambda cfg: alertas, avisar)) == 2       # precio base
    alertas += [oferta(25100, "GDL"), oferta(27000, "QRO")]                       # los viejos se releen
    avisos = agente.revisar(CFG, con, lambda cfg: alertas, avisar)
    assert len(avisos) == 1 and "QRO → MAD" in avisos[0] and "-10 %" in avisos[0]
    assert "108,000 MXN para 4" in avisos[0]
    assert con.execute("SELECT COUNT(*) FROM precios").fetchone()[0] == 4         # sin duplicados
    assert store.minimo_previo(con, "QRO", "MAD") == 27000


def test_error_de_imap_no_rompe(con):
    def leer(cfg):
        raise fuente.FuenteError("IMAP falló")
    assert agente.revisar(CFG, con, leer, lambda t: True) == []


def test_leer_sin_credenciales(monkeypatch):
    monkeypatch.delenv("IMAP_USER", raising=False)
    with pytest.raises(fuente.FuenteError):
        fuente.leer(CFG)


def test_config_real_carga():
    from vuelos.config import load_config
    cfg = load_config()
    assert cfg["origenes"] == ["GDL", "QRO"] and cfg["destinos"] == ["MAD"] and cfg["pasajeros"] == 4
    assert cfg["fechas"]["salida"] == dt.date(2027, 6, 11) and "Querétaro" in cfg["ciudades"]["QRO"]
