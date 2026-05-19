# Gundrux Auto-Poster v2

Posts 3 times daily to Facebook + Instagram + LinkedIn via Buffer.
Telegram approval before every post.

## Stack
- Claude Haiku → captions + tips
- HTML/Playwright → image rendering (3 rotating templates)
- Cloudinary → image hosting
- Buffer GraphQL API → posts to FB + IG + LinkedIn
- Telegram → approval flow
- Railway → hosting + cron

## Features
- 3 posts daily (9 AM, 1 PM, 6 PM India time)
- Telegram approval: Approve / Reject / Edit / Regenerate
- Scrapes 5 blog sources for fresh topics:
  - webdoux.com/blog
  - backlinko.com/blog
  - ahrefs.com/blog
  - moz.com/blog
  - semrush.com/blog
- 3 rotating template designs (Indigo / Purple Split / Neon)
- History tracking (approved & rejected)
- Custom topics support

## Railway Variables Required

```
ANTHROPIC_API_KEY=sk-ant-...
CLOUDINARY_CLOUD=dpibyssay
CLOUDINARY_API_KEY=541523367679521
CLOUDINARY_SECRET=0V7gIESVcHiNmlxyHVXapvDTbXY
BUFFER_TOKEN=j3XZIo0WAMqTczbl7wbnBEGQKRFprbfPX1Y0JM01vyT
TELEGRAM_TOKEN=8895110218:AAEYteT6B-lIDWc96fkFwh57cQ7288S0_zw
TELEGRAM_CHAT_ID=8076792093
```

## Cron Schedule
Runs at: 3:30 AM, 7:30 AM, 12:30 PM UTC = 9 AM, 1 PM, 6 PM India

## Files
- `bot.py` - main script
- `requirements.txt` - dependencies
- `railway.toml` - deployment config
- `custom_topics.txt` - your topics
- `history.json` - auto-generated post log
