"""CLI: python -m vuelos revisar | historial | prueba-telegram"""
import argparse
import logging

from vuelos import agente, notify, store
from vuelos.config import db_path, load_config


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="vuelos")
    p.add_argument("comando", choices=["revisar", "historial", "prueba-telegram"])
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if args.comando == "prueba-telegram":
        ok = notify.telegram("✅ vuelos-baratos: conexión con Telegram correcta", silent=True)
        raise SystemExit(0 if ok else f"Telegram falló: {notify.ultimo_error}")
    con = store.conectar(db_path())
    if args.comando == "revisar":
        avisos = agente.revisar(cfg, con)
        print(f"Revisión terminada: {len(avisos)} aviso(s)")
    else:
        for o in cfg["origenes"]:
            for d in cfg["destinos"]:
                print(f"{o} → {d}")
                for ts, precio in store.historial(con, o, d):
                    print(f"  {ts}  {precio:,.0f} {cfg['moneda'].upper()}")


if __name__ == "__main__":
    main()
