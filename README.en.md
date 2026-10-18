# furima-watch — Price watcher across Japanese flea markets and used-goods shops

[日本語](README.md) | **English** | [简体中文](README.zh-CN.md)

Get a Windows notification the moment the used item you want is listed below your target price.
One run checks 7 sites: Mercari, Yahoo! Auctions, PayPay Flea Market, Rakuma, Janpara, Sofmap and Hard Off.

It started as a way to buy an RTX 4070 Ti SUPER cheaply, but you can watch anything by editing the config file.

## Features

- Searches 7 sites for new listings that fit your price range
- Filters titles with regular expressions so only the actual item remains (no empty boxes, cables, whole gaming PCs or buy-back ads)
- On Yahoo! Auctions, notifies not only buy-it-now prices but also **auctions ending soon whose current bid is low**
- Remembers what it has already notified and never repeats it (notifies again if a price drop brings a listing back into range)
- Clicking a notification opens the listing. With [ntfy.sh](https://ntfy.sh) you also get it on your phone
- If a site keeps failing (for example because its layout changed), it tells you once

## Usage

Requires Python 3.11+ (Windows; notifications use winotify).

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.toml config.toml   # write the items and prices you want
.venv\Scripts\python furima_watch.py --dry-run      # show matches without notifying
.venv\Scripts\python furima_watch.py --test-notify  # preview what a notification looks like
.venv\Scripts\python furima_watch.py                # one pass; notifies on new matches
```

### Run it periodically (Task Scheduler)

The script does one pass and exits, so schedule it every 15–30 minutes.
Using `pythonw.exe` keeps a console window from popping up.

```bash
schtasks /create /tn furima-watch /sc minute /mo 20 /tr "\"C:\path\to\furima-watch\.venv\Scripts\pythonw.exe\" \"C:\path\to\furima-watch\furima_watch.py\""
```

## Configuration (config.toml)

Add one `[[watch]]` block per item. See [config.example.toml](config.example.toml) for a full example.

| Key | Meaning |
|---|---|
| `name` | Name shown in notifications |
| `queries` | Search terms for the flea markets and auctions (several allowed) |
| `shop_query` | Search term for Janpara, Sofmap and Hard Off (defaults to the first of `queries`) |
| `min_price` / `max_price` | Price range in yen. A lower bound is recommended: very cheap listings are usually boxes or cables |
| `target` | A listing counts if its title matches any of these (list of regexes; empty = every search result) |
| `exclude` | A listing is dropped if its title matches any of these |
| `include_junk` | Whether to include junk / for-parts listings |

Titles are NFKC-normalized and lowercased before matching, so full-width characters become half-width. Write patterns in half-width characters.

## Notes

- It uses unofficial ways of reading each site, so a site change can break it.
- Keep it to personal use and a generous interval, so you don't put load on the sites. Check each site's terms of service yourself.
- Always look at the listing yourself before buying.

## License

MIT
