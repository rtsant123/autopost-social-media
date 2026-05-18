# Gundrux Instagram Auto Poster

Posts 6 AI-generated images daily to Instagram automatically.

## Stack
- Claude Haiku → captions + image prompts
- Replicate Flux → image generation (~$0.003/image)
- Cloudinary → image hosting (free)
- Meta Graph API → Instagram posting (free)
- Railway → hosting + cron ($5/month)

## Railway Environment Variables

| Variable | Value |
|---|---|
| REPLICATE_API_TOKEN | r8_PIGxGEdvRbiLng7Aho5cOzLz8Yg4Ahr39bMN2 |
| CLOUDINARY_CLOUD | dpibyssay |
| CLOUDINARY_API_KEY | 541523367679521 |
| CLOUDINARY_SECRET | 0V7gIESVcHiNmlxyHVXapvDTbXY |
| IG_USER_ID | 122131959087016967 |
| IG_ACCESS_TOKEN | your_token_here |
| ANTHROPIC_API_KEY | your_key_here |
| LOGO_URL | https://yoursite.com/logo.png (optional) |

## Add Your Own Topics

Edit `custom_topics.txt` — one topic per line.
They auto-mix with the 30 default topics.

## Logo Watermark

Set `LOGO_URL` in Railway variables to your logo image URL.
If not set, it will use text watermark `gundrux.in` instead.

## Deploy to Railway

1. Push this folder to GitHub
2. Railway → New Project → Deploy from GitHub
3. Add all environment variables
4. Set cron: `0 6 * * *` (runs 6 AM UTC daily)

## Cost

~$6-7/month total (Railway + Replicate)
