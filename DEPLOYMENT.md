# Hosting the bot 24/7

🇫🇷 [Version française](DEPLOYMENT.fr.md)

A Discord bot must stay connected at all times: it needs a machine that
never turns off. Honest state of play in 2026: "unlimited free with no
credit card" has all but disappeared. Here are the options, from simplest
to most robust.

## Option 0 — Your PC (development only)

Free and instant: `python -m bot.main` and the bot is online... as long as
the PC is on. Great for developing and testing, not for the guild.

## Option 1 — Railway (simplest)

[Railway](https://railway.com) deploys straight from GitHub: connect the
repo, it detects the `Dockerfile`, and every `git push` redeploys.

1. Create an account on railway.com (GitHub sign-in).
2. **New Project → Deploy from GitHub repo** → pick `aion2-group-bot`.
3. Under **Variables**, add at least:
   - `DISCORD_TOKEN` — the bot token.
   - `TIMEZONE=Europe/Madrid` — or the timezone your community uses.
   - `DB_PATH=/app/data/bot.db`.
   - `PLAYNC_REFRESH_MINUTES=60`.
   - Leave `GUILD_ID` **empty for a public multi-server bot**. Set it only
     during development when you want commands synced to one test server.
4. Add a **Volume** mounted on `/app/data` so the SQLite database survives
   redeployments.

Railway currently offers a Free plan for small projects and a Hobby plan with
a $5 minimum monthly usage commitment. Free/Trial volumes are limited to
0.5 GB; Hobby includes up to 5 GB of volume storage. For a public bot where
uptime matters, Hobby is the safer default. Check Railway's current pricing
before deploying because plan limits can change.

## Option 2 — Oracle Cloud Free Tier (actually free, more technical)

Oracle's Always Free tier currently includes Ampere A1 compute within a
monthly allowance equivalent to up to 2 OCPUs and 12 GB of memory, plus
Always Free block storage. That is more than enough for this bot for $0.
There is no SLA or paid support on the free tier, capacity can be unavailable,
and it is a real Linux server you must administer.

1. Create an account at <https://www.oracle.com/cloud/free/> and launch an
   **Ampere A1** instance (Ubuntu).
2. SSH in, then:

```bash
sudo apt update && sudo apt install -y python3-venv git
git clone https://github.com/Akreutler/aion2-group-bot.git
cd aion2-group-bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env   # paste your token
```

3. Create a systemd service so it starts automatically
   (`sudo nano /etc/systemd/system/aion2bot.service`):

```ini
[Unit]
Description=Aion 2 Discord bot
After=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/aion2-group-bot
ExecStart=/home/ubuntu/aion2-group-bot/.venv/bin/python -m bot.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now aion2bot
journalctl -u aion2bot -f     # watch the logs
```

## Option 3 — A classic VPS (~$5/month)

Hetzner, OVH, Contabo...: same steps as option 2 (it's also a Linux
server), without Oracle's quirks. Simple, reliable, not free.

## What to avoid for a bot

- **Render (free plan)**: free web services go to sleep after 15 minutes of
  inactivity, which knocks the bot offline. Their "background worker" tier
  that would fit is paid.
- **Fly.io**: no more free tier for new accounts.
- **Replit / "uptime robots"**: unstable hacks — avoid for a guild bot that
  must be reliable on raid night.

## In every case

- The `data/bot.db` file holds every event: on container platforms, mount a
  persistent volume on `/app/data`, or everything is lost on each redeploy.
- **Never** put the token in the code or on GitHub: always an environment
  variable (local `.env` file, "Variables" at your host).


## Public multi-server deployment

One running Kisk process can serve many Discord servers. Do **not** launch one
copy per guild. Data is scoped by Discord `guild_id` in SQLite.

For the public bot:

1. Leave `GUILD_ID` empty so slash commands are registered globally.
2. In Discord Developer Portal, keep **Public Bot** enabled.
3. The installation URL needs the `bot` and `applications.commands` scopes
   plus Kisk's required channel/thread permissions.
4. Keep one persistent `/app/data` volume. All guilds share the same database
   file, but their settings, profiles and events remain guild-scoped.
5. Keep the bot token in the hosting provider's secret/environment settings,
   never in GitHub.

Kisk deliberately uses a guild-neutral Discord presence. A public bot must not
show one server's event title to every other server it belongs to.
