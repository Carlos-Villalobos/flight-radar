# vuelos-baratos

Agente que vigila el precio de los vuelos **Guadalajara (GDL) y Querétaro (QRO) → Madrid (MAD)**, ida y vuelta,
para **4 adultos**, del vie 11 al dom 27 de junio de 2027. Lee las **alertas de precio de Google Flights** que
llegan a tu Gmail, guarda el histórico en SQLite y avisa por Telegram cuando el precio de una ruta **baja**.

Sin APIs ni scraping. Sigue la estructura de [job-radar](../job-radar) y reutiliza su forma de leer el correo
(`linkedin_email.py`): IMAP en **solo lectura** (`readonly=True` + `BODY.PEEK`), que no marca, mueve ni borra
correos, con una contraseña de aplicación de Gmail.

## Cómo funciona

1. En Google Flights activas el **seguimiento de precio** de cada ruta (GDL → MAD y QRO → MAD, 4 adultos,
   11 → 27 jun 2027) con la cuenta de Gmail de `IMAP_USER`. Google manda un correo cuando el precio cambia.
2. `python -m vuelos revisar` lee las alertas de los últimos 7 días, reconoce la ruta por el nombre de las
   ciudades (`ciudades` en el config) y saca el precio en MXN y el enlace a Google Flights.
3. Cada correo se procesa una sola vez (por su `Message-ID`) y se guarda en `data/precios.sqlite`.
4. Compara con el **mínimo visto antes** en esa ruta: la primera vez manda el precio de partida; después solo
   avisa si baja al menos un `bajada_minima_pct` (3 %).

> **Parser provisional.** El formato del correo de Google no está documentado. Hasta tener un correo real se
> asume que muestra el precio **total** de los 4 (`precio_del_correo: total`) y, si aparecen precio anterior y
> nuevo, se queda con el más bajo. Cuando llegue la primera alerta, descárgala como `.eml` (Gmail: ⋮ →
> Descargar mensaje) para ajustar el parser y añadirla a los tests.

## Puesta en marcha (paso a paso)

1. **Alertas:** crea en Google Flights los dos seguimientos de precio (paso 1 de arriba).
2. **`.env`:** se puede copiar el de job-radar (`cp ../job-radar/.env .env`): usa las mismas `IMAP_*` y
   `TELEGRAM_*`. Las alertas tienen que llegar a ese Gmail.
3. **Instala el proyecto:**
   ```bash
   uv venv -p 3.12 .venv && uv pip install -p .venv -e '.[dev]'
   ```
   En macOS, si luego sale `No module named vuelos`, quita la marca de oculto que pone la sincronización de
   `~/Documents`: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth`.
4. **Prueba Telegram y una revisión:**
   ```bash
   .venv/bin/python -m vuelos prueba-telegram
   .venv/bin/python -m vuelos revisar
   .venv/bin/python -m vuelos historial
   ```

## En la EC2

```bash
git clone <tu-repo> ~/vuelos-baratos && cd ~/vuelos-baratos
uv venv -p 3.12 .venv && uv pip install -p .venv -e .
cp .env.example .env    # y complétalo
./scripts/install_systemd.sh
```

El timer revisa 3 veces al día (09:20, 15:20 y 20:40, hora de Madrid): cada ~6 h dentro del horario en que la EC2
está encendida, igual que job-radar. Si estaba apagada, corre al arrancar (`Persistent=true`). Para ver los logs:
`journalctl -u vuelos-revisar.service -n 50 --no-pager`. Para quitarlo: `./scripts/install_systemd.sh uninstall`.

## Cambiar el viaje

Todo está en [`config/viaje.yaml`](config/viaje.yaml): orígenes, destinos, fechas, pasajeros, nombres de las
ciudades, si el correo trae precio total o por persona, precio máximo y % mínimo de bajada. Si cambias fechas o
pasajeros, cambia también los seguimientos en Google Flights.

## Pruebas

```bash
.venv/bin/pytest -q
```

No leen el correo ni llaman a Telegram: se simulan con correos de ejemplo.
