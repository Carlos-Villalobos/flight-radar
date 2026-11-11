# flight-radar

Watches round-trip flight prices from **Google Flights price-tracking emails**. It reads the alerts from Gmail,
keeps the price history in SQLite and sends a Telegram message when the price of a route **drops**.

No APIs and no scraping: Google Flights does the tracking, and this agent reads your inbox over IMAP in
**read-only** mode (`readonly=True` + `BODY.PEEK`), so it never marks, moves or deletes emails.

## How it works

1. In Google Flights, turn on **price tracking** for each route (same dates and passengers as in
   `config/trip.yaml`) using the Gmail account in `IMAP_USER`. Google emails you when the price changes.
2. `python -m flight_radar check` reads the alerts from the last 7 days, matches each route by city name
   (`cities` in the config) and extracts the MXN price and the Google Flights link.
3. Each email is processed once (by its `Message-ID`) and stored in `data/prices.sqlite`.
4. It compares against the **lowest price seen before** on that route: the first time it sends the starting
   price; after that it only notifies when the price drops at least `min_drop_pct` (3 %).

> **Provisional parser.** Google's alert format is undocumented. Until it is checked against a real email, it
> assumes the alert shows the **total** price for all passengers (`email_price: total`) and, if both the old and
> the new price appear, it keeps the lowest one.

## Setup

1. **Trip:** copy the example and edit it (`config/trip.yaml` is git-ignored):
   ```bash
   cp config/trip.example.yaml config/trip.yaml
   ```
2. **Alerts:** track each route in Google Flights (step 1 above).
3. **Secrets:** create `.env` from the template and fill it in:
   ```bash
   cp .env.example .env
   ```
   `IMAP_PASSWORD` must be a Gmail **app password** (Google Account → Security → App passwords).
4. **Install:**
   ```bash
   uv venv -p 3.12 .venv && uv pip install -p .venv -e '.[dev]'
   ```
   On macOS, if you later get `No module named flight_radar` inside a synced `~/Documents` folder, remove the
   hidden flag: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth`.
5. **Try it:**
   ```bash
   .venv/bin/python -m flight_radar test-telegram
   .venv/bin/python -m flight_radar check
   .venv/bin/python -m flight_radar history
   ```

## Running on a server (systemd)

```bash
git clone https://github.com/Carlos-Villalobos/Flight_radar.git ~/flight-radar && cd ~/flight-radar
uv venv -p 3.12 .venv && uv pip install -p .venv -e .
cp .env.example .env                              # and fill it in
cp config/trip.example.yaml config/trip.yaml      # and edit it
./scripts/install_systemd.sh
```

The timer checks 3 times a day (09:20, 15:20 and 20:40, Madrid time). If the machine was off at a scheduled time,
it runs at boot (`Persistent=true`). Logs: `journalctl -u flight-radar-check.service -n 50 --no-pager`.
To remove it: `./scripts/install_systemd.sh uninstall`.

## Tests

```bash
.venv/bin/pytest -q
```

They never read real email or call Telegram: both are simulated with sample messages.
