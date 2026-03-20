# cloudflare-ddns

A DDNS script that syncs the current global IP to Cloudflare DNS A/AAAA/CNAME records.

## Setup

```bash
cp config.example.json config.json
# Edit config.json
uv run python main.py
```

## config.json

```json
{
  "api_token": "Cloudflare API token",
  "ttl": 1,
  "proxied": false,
  "enable_ipv4": true,
  "enable_ipv6": false,
  "records": [
    { "zone_id": "Zone ID", "name": "home.example.com" },
    { "zone_id": "Zone ID", "name": "sub.example.com" },
    { "zone_id": "zone_id_for_example_com", "name": "alias.example.com", "cname_target": "home.example.com"
    }
  ]
}
```

`ttl: 1` = Auto. Supports multiple records and multiple zones.

## crontab

```crontab
*/15 * * * * cd /path/to/domain && /home/user/.local/bin/uv run python main.py >> ~/ddns.log 2>&1
```
