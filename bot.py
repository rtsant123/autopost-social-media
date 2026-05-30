import sys
import os
import time

# Force unbuffered output for Railway logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import re
import json
import random
import requests
import cloudinary
import cloudinary.uploader
from datetime import datetime, date, timezone, timedelta
import anthropic
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# ── CONFIG ────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
CLOUDINARY_CLOUD   = os.environ["CLOUDINARY_CLOUD"]
CLOUDINARY_KEY     = os.environ["CLOUDINARY_API_KEY"]
CLOUDINARY_SECRET  = os.environ["CLOUDINARY_SECRET"]
BUFFER_TOKEN       = os.environ["BUFFER_TOKEN"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

# Buffer channels
BUFFER_FB_CHANNEL  = "6a0b3f9e090476fb9932d776"
BUFFER_IG_CHANNEL  = "6a0b4005090476fb9932d92e"
BUFFER_LI_CHANNEL  = "6a0bf7b7090476fb99360b4e"  # Gundrux company page

# India timezone
IST = timezone(timedelta(hours=5, minutes=30))

# ── DAILY SCHEDULE (India time) ───────────────────────────
# type:           "single" or "carousel"
# manual_caption: True  -> bot builds images, then WAITS for you to send a caption.
#                          If you don't send one, the post is NOT published.
#                 False -> Claude writes the caption automatically.
# To make the 6 PM post a single instead of a carousel, change its "type" to "single".
SCHEDULE = [
    {"time": "09:00", "type": "single",   "manual_caption": False},
    {"time": "13:00", "type": "single",   "manual_caption": False},
    {"time": "18:00", "type": "carousel", "manual_caption": True},
]

# A carousel = 1 cover slide showing ONE tip + this many detail slides = 5 images total.
CAROUSEL_DETAIL_SLIDES = 4

# How long a manual-caption post waits for your caption before it's dropped (not posted).
MANUAL_CAPTION_EXPIRY_HOURS = 4

# Blog sources to scrape topics from
BLOG_SOURCES = [
    "https://webdoux.com/blog/",
    "https://backlinko.com/blog",
    "https://ahrefs.com/blog/",
    "https://moz.com/blog",
    "https://www.semrush.com/blog/",
]

CUSTOM_TOPICS_FILE = "custom_topics.txt"
HISTORY_FILE       = "history.json"

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD,
    api_key=CLOUDINARY_KEY,
    api_secret=CLOUDINARY_SECRET
)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ── TELEGRAM HELPERS ─────────────────────────────────────
def tg_send(text, reply_markup=None):
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        return requests.post(f"{TELEGRAM_API}/sendMessage", json=data, timeout=30).json()
    except Exception as e:
        print(f"[telegram] send ERROR: {e}")
        return {"ok": False, "error": str(e)}

def tg_send_photo(image_url, caption, reply_markup=None):
    data = {"chat_id": TELEGRAM_CHAT_ID, "photo": image_url,
            "caption": caption[:1024], "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        return requests.post(f"{TELEGRAM_API}/sendPhoto", json=data, timeout=30).json()
    except Exception as e:
        print(f"[telegram] photo ERROR: {e}")
        return {"ok": False, "error": str(e)}

def tg_send_media_group(image_urls):
    """Send up to 10 images as one swipeable album. No buttons allowed on albums."""
    media = [{"type": "photo", "media": u} for u in image_urls[:10]]
    data = {"chat_id": TELEGRAM_CHAT_ID, "media": json.dumps(media)}
    try:
        return requests.post(f"{TELEGRAM_API}/sendMediaGroup", json=data, timeout=60).json()
    except Exception as e:
        print(f"[telegram] media group ERROR: {e}")
        return {"ok": False, "error": str(e)}

def tg_answer_callback(callback_id, text=""):
    try:
        requests.post(f"{TELEGRAM_API}/answerCallbackQuery",
                      json={"callback_query_id": callback_id, "text": text}, timeout=15)
    except Exception:
        pass

def tg_get_updates(offset=0, timeout=10):
    try:
        resp = requests.get(f"{TELEGRAM_API}/getUpdates",
                            params={"offset": offset, "timeout": timeout},
                            timeout=timeout + 10)
        return resp.json().get("result", [])
    except Exception:
        return []

# ── HISTORY ──────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(entry):
    history = load_history()
    history.append(entry)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

# ── TOPIC SCRAPING (MULTI-SOURCE) ────────────────────────
def scrape_topics_from(url):
    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0 (compatible; Bot)"})
        soup = BeautifulSoup(resp.text, "html.parser")
        titles = []
        for tag in soup.find_all(["h2", "h3", "h1", "a"]):
            text = tag.get_text(strip=True)
            if not (25 < len(text) < 130):
                continue
            if text.lower().startswith(("subscribe", "sign up", "log in", "menu")):
                continue
            brands = ["ahrefs", "moz", "semrush", "backlinko", "webdoux", "course by",
                      "| 3.", "| 2.", "| 1.", " by ", "feat.", "ft.", "podcast"]
            if any(b in text.lower() for b in brands):
                continue
            text = text.split(" | ")[0].split(" - ")[0].strip()
            if 20 < len(text) < 100:
                titles.append(text)
        return titles[:15]
    except Exception as e:
        print(f"Scrape {url} failed: {e}")
        return []

def scrape_all_sources():
    all_topics = []
    for url in BLOG_SOURCES:
        topics = scrape_topics_from(url)
        print(f"  {url} -> {len(topics)} topics")
        all_topics.extend(topics)
    return all_topics

DEFAULT_TOPICS = [
    "SEO tips for small businesses in 2026",
    "WordPress speed optimization guide",
    "Social media content strategy for brands",
    "Google ranking factors you must know",
    "On-page SEO checklist for beginners",
    "WordPress plugins every business needs",
    "Instagram growth tips for digital agencies",
    "Local SEO strategies that actually work",
    "Content marketing for B2B companies",
    "Technical SEO basics explained",
    "How to use AI for content creation",
    "Common WordPress mistakes to avoid",
    "How to grow a brand on Instagram",
    "Core Web Vitals explained simply",
    "Voice search optimization tips",
    "AI automation for digital marketing agencies",
    "Best AI tools for SEO in 2026",
    "How to do keyword research with AI",
    "Schema markup for better rankings",
    "Link building strategies that work today",
]

def load_topics():
    print("Scraping topics from blog sources...")
    topics = scrape_all_sources()
    if os.path.exists(CUSTOM_TOPICS_FILE):
        with open(CUSTOM_TOPICS_FILE) as f:
            custom = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            topics.extend(custom)
            print(f"  Custom topics: {len(custom)}")
    if len(topics) < 10:
        topics.extend(DEFAULT_TOPICS)
    history = load_history()
    posted = {h.get("topic", "").lower() for h in history if h.get("status") == "approved"}
    fresh = [t for t in set(topics) if t.lower() not in posted]
    print(f"  Total fresh topics: {len(fresh)}")
    return fresh if fresh else list(set(topics))

def pick_topic():
    topics = load_topics()
    return random.choice(topics) if topics else random.choice(DEFAULT_TOPICS)

# ── CLAUDE: SINGLE POST CONTENT (5 tips on one image) ─────
def _claude_json(prompt, max_retries=4):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception as e:
            err = str(e)
            if "overloaded" in err.lower() or "529" in err or "rate" in err.lower():
                wait = 10 * (attempt + 1)
                print(f"  Claude overloaded, retry {attempt+1}/{max_retries} in {wait}s...")
                time.sleep(wait)
                continue
            raise
    raise Exception("Claude API still overloaded after retries")

def generate_single_content(topic):
    prompt = (
        f"You are a social media expert for Gundrux, a digital marketing agency "
        f"specializing in AI SEO, WordPress, social media growth, and AI automation.\n\n"
        f"Topic: {topic}\n\n"
        f"Return pure JSON only with these keys:\n"
        f"1. title: punchy title max 8 words in English\n"
        f"2. points: exactly 5 actionable tips in English max 12 words each\n"
        f"3. caption: 2-3 engaging lines for social media in English\n"
        f"4. hashtags: 15 relevant hashtags as single string starting with #\n"
        f"5. category: pick one: SEO TIPS / WORDPRESS / SOCIAL MEDIA / AI MARKETING / CONTENT GROWTH\n\n"
        f"Pure JSON only. No markdown."
    )
    data = _claude_json(prompt)
    pts = list(data.get("points", []))
    while len(pts) < 5:
        pts.append("Stay consistent and track your results daily")
    data["points"] = pts[:5]
    return data

# ── CLAUDE: CAROUSEL CONTENT (ONE tip told across 5 images) ─
def generate_carousel_content(topic):
    prompt = (
        f"You are a social media expert for Gundrux, a digital marketing agency "
        f"(AI SEO, WordPress, social media growth, AI automation).\n\n"
        f"Topic: {topic}\n\n"
        f"Design an Instagram carousel that teaches ONE single tip, told across 5 slides. "
        f"Slide 1 is the cover (the tip itself). The next 4 slides break that SAME one tip "
        f"into clear steps/reasons/examples. Do NOT introduce different tips.\n\n"
        f"Return pure JSON only with these keys:\n"
        f'1. tip: the one core tip, max 9 words (this is the cover headline)\n'
        f'2. category: pick one: SEO TIPS / WORDPRESS / SOCIAL MEDIA / AI MARKETING / CONTENT GROWTH\n'
        f'3. slides: exactly 4 objects, each {{"heading": "max 5 words", "body": "max 16 words"}}, '
        f'   each expanding the SAME single tip step by step\n'
        f'4. caption: 2-3 engaging lines for social media\n'
        f'5. hashtags: 15 relevant hashtags as single string starting with #\n\n'
        f"All English. Pure JSON only. No markdown."
    )
    data = _claude_json(prompt)
    slides = list(data.get("slides", []))
    while len(slides) < CAROUSEL_DETAIL_SLIDES:
        slides.append({"heading": "Pro tip", "body": "Stay consistent and measure your results every week."})
    data["slides"] = slides[:CAROUSEL_DETAIL_SLIDES]
    if not data.get("tip"):
        data["tip"] = data.get("title", topic)
    return data

# ══════════════════════════════════════════════════════════
#  SINGLE-POST TEMPLATES (unchanged)
# ══════════════════════════════════════════════════════════
TEMPLATE_DARK_INDIGO = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'Inter',sans-serif;}}
.post{{width:1080px;height:1080px;background:linear-gradient(135deg,#0D0D1A 0%,#0A0A14 60%,#0D0A1F 100%);position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;padding:48px 56px;}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(99,102,241,0.05) 1px,transparent 1px),linear-gradient(90deg,rgba(99,102,241,0.05) 1px,transparent 1px);background-size:80px 80px;pointer-events:none;}}
.watermark{{position:absolute;bottom:-30px;left:-20px;font-size:220px;font-weight:900;color:rgba(99,102,241,0.06);letter-spacing:-8px;pointer-events:none;z-index:1;white-space:nowrap;}}
.glow1{{position:absolute;top:-150px;left:-150px;width:600px;height:600px;background:radial-gradient(circle,rgba(99,102,241,0.18) 0%,transparent 70%);}}
.glow2{{position:absolute;bottom:-150px;right:-100px;width:500px;height:500px;background:radial-gradient(circle,rgba(139,92,246,0.12) 0%,transparent 70%);}}
.top-bar{{display:flex;justify-content:space-between;align-items:center;position:relative;z-index:10;}}
.logo img{{height:34px;object-fit:contain;}}
.tag{{background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.5);color:#A5B4FC;font-size:15px;font-weight:700;letter-spacing:2px;padding:8px 20px;border-radius:100px;}}
.main{{position:relative;z-index:10;flex:1;display:flex;flex-direction:column;justify-content:center;}}
.category{{font-size:15px;font-weight:700;color:#6366F1;letter-spacing:3px;text-transform:uppercase;margin-bottom:14px;display:flex;align-items:center;gap:10px;}}
.category::before{{content:'';display:block;width:28px;height:2px;background:#6366F1;}}
.title{{font-size:72px;font-weight:900;color:#FFFFFF;line-height:1.05;letter-spacing:-2px;margin-bottom:24px;}}
.title .hl{{background:linear-gradient(90deg,#818CF8,#C084FC);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
.divider{{width:60px;height:3px;background:linear-gradient(90deg,#6366F1,transparent);margin-bottom:24px;}}
.points{{display:flex;flex-direction:column;gap:14px;}}
.point{{display:flex;align-items:flex-start;gap:16px;}}
.point-num{{min-width:38px;height:38px;background:linear-gradient(135deg,#6366F1,#8B5CF6);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:white;flex-shrink:0;margin-top:4px;box-shadow:0 0 16px rgba(99,102,241,0.4);}}
.point-text{{font-size:30px;font-weight:500;color:#CBD5E1;line-height:1.35;}}
.bottom{{display:flex;justify-content:space-between;align-items:center;position:relative;z-index:10;border-top:1px solid rgba(255,255,255,0.07);padding-top:20px;}}
.domain{{font-size:22px;font-weight:800;color:#6366F1;}}
.services{{font-size:17px;color:#475569;}}
</style></head><body>
<div class="post">
  <div class="grid"></div><div class="glow1"></div><div class="glow2"></div>
  <div class="watermark">GUNDRUX</div>
  <div class="top-bar">
    <div class="logo"><img src="https://gundrux.in/wp-content/uploads/2026/03/cropped-cropped-ChatGPT_Image_Mar_21__2026__02_13_51_PM-removebg-preview-1-250x42.png" /></div>
    <div class="tag">{category}</div>
  </div>
  <div class="main">
    <div class="category">{category}</div>
    <div class="title">{title_line1}<br><span class="hl">{title_line2}</span></div>
    <div class="divider"></div>
    <div class="points">
      <div class="point"><div class="point-num">01</div><div class="point-text">{p1}</div></div>
      <div class="point"><div class="point-num">02</div><div class="point-text">{p2}</div></div>
      <div class="point"><div class="point-num">03</div><div class="point-text">{p3}</div></div>
      <div class="point"><div class="point-num">04</div><div class="point-text">{p4}</div></div>
      <div class="point"><div class="point-num">05</div><div class="point-text">{p5}</div></div>
    </div>
  </div>
  <div class="bottom">
    <div class="domain">gundrux.in</div>
    <div class="services">AI SEO &middot; AEO &middot; GEO &middot; Brand Growth</div>
  </div>
</div></body></html>"""

TEMPLATE_MINIMAL_NEON = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'Inter',sans-serif;}}
.post{{width:1080px;height:1080px;background:#08080C;position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;padding:48px 56px;}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(34,211,238,0.04) 1px,transparent 1px),linear-gradient(90deg,rgba(34,211,238,0.04) 1px,transparent 1px);background-size:60px 60px;}}
.glow1{{position:absolute;top:-200px;right:-100px;width:500px;height:500px;background:radial-gradient(circle,rgba(34,211,238,0.15) 0%,transparent 70%);}}
.glow2{{position:absolute;bottom:-200px;left:-100px;width:600px;height:600px;background:radial-gradient(circle,rgba(99,102,241,0.12) 0%,transparent 70%);}}
.watermark{{position:absolute;right:-30px;top:50%;transform:translateY(-50%) rotate(-90deg);font-size:200px;font-weight:900;color:rgba(34,211,238,0.04);letter-spacing:-6px;pointer-events:none;}}
.top-bar{{display:flex;justify-content:space-between;align-items:center;position:relative;z-index:10;}}
.logo img{{height:34px;}}
.tag{{background:rgba(34,211,238,0.15);border:1px solid rgba(34,211,238,0.4);color:#67E8F9;font-size:15px;font-weight:700;letter-spacing:2px;padding:8px 20px;border-radius:8px;}}
.main{{position:relative;z-index:10;flex:1;display:flex;flex-direction:column;justify-content:center;}}
.bar{{display:flex;align-items:center;gap:14px;margin-bottom:18px;}}
.bar-line{{width:50px;height:3px;background:#22D3EE;}}
.bar-text{{font-size:15px;font-weight:700;color:#22D3EE;letter-spacing:3px;text-transform:uppercase;}}
.title{{font-size:74px;font-weight:900;color:#FFFFFF;line-height:1.05;letter-spacing:-2px;margin-bottom:30px;}}
.title .hl{{color:#22D3EE;text-shadow:0 0 30px rgba(34,211,238,0.4);}}
.points{{display:flex;flex-direction:column;gap:18px;}}
.point{{display:flex;align-items:flex-start;gap:18px;}}
.point-bar{{min-width:6px;height:42px;background:#22D3EE;flex-shrink:0;margin-top:4px;box-shadow:0 0 15px rgba(34,211,238,0.5);}}
.point-text{{font-size:30px;font-weight:500;color:#E2E8F0;line-height:1.35;}}
.bottom{{display:flex;justify-content:space-between;align-items:center;position:relative;z-index:10;padding-top:24px;border-top:1px solid rgba(34,211,238,0.15);}}
.domain{{font-size:24px;font-weight:800;color:#22D3EE;text-shadow:0 0 20px rgba(34,211,238,0.4);}}
.services{{font-size:17px;color:#64748B;}}
</style></head><body>
<div class="post">
  <div class="grid"></div><div class="glow1"></div><div class="glow2"></div>
  <div class="watermark">GUNDRUX</div>
  <div class="top-bar">
    <div class="logo"><img src="https://gundrux.in/wp-content/uploads/2026/03/cropped-cropped-ChatGPT_Image_Mar_21__2026__02_13_51_PM-removebg-preview-1-250x42.png" /></div>
    <div class="tag">{category}</div>
  </div>
  <div class="main">
    <div class="bar"><div class="bar-line"></div><div class="bar-text">{category}</div></div>
    <div class="title">{title_line1}<br><span class="hl">{title_line2}</span></div>
    <div class="points">
      <div class="point"><div class="point-bar"></div><div class="point-text">{p1}</div></div>
      <div class="point"><div class="point-bar"></div><div class="point-text">{p2}</div></div>
      <div class="point"><div class="point-bar"></div><div class="point-text">{p3}</div></div>
      <div class="point"><div class="point-bar"></div><div class="point-text">{p4}</div></div>
      <div class="point"><div class="point-bar"></div><div class="point-text">{p5}</div></div>
    </div>
  </div>
  <div class="bottom">
    <div class="domain">gundrux.in</div>
    <div class="services">AI SEO &middot; AEO &middot; GEO &middot; Brand Growth</div>
  </div>
</div></body></html>"""

def template_dark_indigo(c):  return TEMPLATE_DARK_INDIGO.format(**c)
def template_minimal_neon(c): return TEMPLATE_MINIMAL_NEON.format(**c)
TEMPLATES = [template_dark_indigo, template_minimal_neon]

# ══════════════════════════════════════════════════════════
#  CAROUSEL TEMPLATES — cover (the one tip) + detail slides
# ══════════════════════════════════════════════════════════
CAROUSEL_COVER = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'Inter',sans-serif;}}
.post{{width:1080px;height:1080px;background:linear-gradient(135deg,#0D0D1A 0%,#0A0A14 55%,#15102B 100%);position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:center;padding:70px 64px;}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(99,102,241,0.05) 1px,transparent 1px),linear-gradient(90deg,rgba(99,102,241,0.05) 1px,transparent 1px);background-size:80px 80px;}}
.glow1{{position:absolute;top:-150px;left:-150px;width:650px;height:650px;background:radial-gradient(circle,rgba(99,102,241,0.20) 0%,transparent 70%);}}
.glow2{{position:absolute;bottom:-180px;right:-120px;width:560px;height:560px;background:radial-gradient(circle,rgba(139,92,246,0.14) 0%,transparent 70%);}}
.watermark{{position:absolute;bottom:-40px;left:-25px;font-size:240px;font-weight:900;color:rgba(99,102,241,0.06);letter-spacing:-8px;}}
.logo img{{height:40px;position:relative;z-index:10;}}
.counter{{position:absolute;top:64px;right:64px;font-size:22px;font-weight:700;color:#6366F1;letter-spacing:2px;z-index:10;}}
.tag{{display:inline-block;background:rgba(99,102,241,0.2);border:1px solid rgba(99,102,241,0.5);color:#A5B4FC;font-size:17px;font-weight:700;letter-spacing:3px;padding:10px 24px;border-radius:100px;margin-top:34px;width:fit-content;position:relative;z-index:10;}}
.title{{font-size:92px;font-weight:900;color:#FFFFFF;line-height:1.03;letter-spacing:-3px;margin-top:34px;position:relative;z-index:10;}}
.title .hl{{background:linear-gradient(90deg,#818CF8,#C084FC);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
.swipe{{position:absolute;bottom:64px;right:64px;display:flex;align-items:center;gap:14px;color:#A5B4FC;font-size:24px;font-weight:700;z-index:10;}}
.swipe-arrow{{font-size:34px;}}
.domain{{position:absolute;bottom:64px;left:64px;font-size:26px;font-weight:800;color:#6366F1;z-index:10;}}
</style></head><body>
<div class="post">
  <div class="grid"></div><div class="glow1"></div><div class="glow2"></div>
  <div class="watermark">GUNDRUX</div>
  <div class="logo"><img src="https://gundrux.in/wp-content/uploads/2026/03/cropped-cropped-ChatGPT_Image_Mar_21__2026__02_13_51_PM-removebg-preview-1-250x42.png" /></div>
  <div class="counter">{counter}</div>
  <div class="tag">{category}</div>
  <div class="title">{title_line1}<br><span class="hl">{title_line2}</span></div>
  <div class="domain">gundrux.in</div>
  <div class="swipe">SWIPE <span class="swipe-arrow">&rarr;</span></div>
</div></body></html>"""

CAROUSEL_DETAIL = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'Inter',sans-serif;}}
.post{{width:1080px;height:1080px;background:linear-gradient(135deg,#0A0A14 0%,#0D0D1A 100%);position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:center;padding:80px 70px;}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(99,102,241,0.05) 1px,transparent 1px),linear-gradient(90deg,rgba(99,102,241,0.05) 1px,transparent 1px);background-size:80px 80px;}}
.glow{{position:absolute;top:-150px;right:-120px;width:560px;height:560px;background:radial-gradient(circle,rgba(99,102,241,0.16) 0%,transparent 70%);}}
.bignum{{position:absolute;top:50px;left:64px;font-size:210px;font-weight:900;color:rgba(99,102,241,0.10);line-height:1;letter-spacing:-10px;z-index:1;}}
.counter{{position:absolute;top:64px;right:70px;font-size:22px;font-weight:700;color:#6366F1;letter-spacing:2px;z-index:10;}}
.numbox{{width:84px;height:84px;background:linear-gradient(135deg,#6366F1,#8B5CF6);border-radius:20px;display:flex;align-items:center;justify-content:center;font-size:36px;font-weight:900;color:white;box-shadow:0 0 30px rgba(99,102,241,0.45);position:relative;z-index:10;}}
.heading{{font-size:56px;font-weight:900;color:#FFFFFF;line-height:1.1;letter-spacing:-1px;margin-top:34px;position:relative;z-index:10;}}
.heading .hl{{background:linear-gradient(90deg,#818CF8,#C084FC);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
.body{{font-size:38px;font-weight:500;color:#CBD5E1;line-height:1.4;margin-top:24px;position:relative;z-index:10;}}
.domain{{position:absolute;bottom:64px;left:70px;font-size:24px;font-weight:800;color:#6366F1;z-index:10;}}
.brand{{position:absolute;bottom:64px;right:70px;font-size:18px;color:#475569;z-index:10;}}
</style></head><body>
<div class="post">
  <div class="grid"></div><div class="glow"></div>
  <div class="bignum">{num}</div>
  <div class="counter">{counter}</div>
  <div class="numbox">{num}</div>
  <div class="heading"><span class="hl">{heading}</span></div>
  <div class="body">{body}</div>
  <div class="domain">gundrux.in</div>
  <div class="brand">AI SEO &middot; AEO &middot; GEO</div>
</div></body></html>"""

# ── RENDERING ─────────────────────────────────────────────
def _split_title(title):
    words = title.split()
    mid = max(1, len(words) // 2)
    return " ".join(words[:mid]), " ".join(words[mid:])

def _screenshot_html(page, html):
    with open("/tmp/render.html", "w") as f:
        f.write(html)
    page.goto("file:///tmp/render.html", timeout=15000)
    page.wait_for_timeout(1500)
    return page.screenshot(full_page=False)

def render_single(content_data):
    line1, line2 = _split_title(content_data["title"])
    points = content_data["points"]
    data = {
        "category": content_data.get("category", "DIGITAL MARKETING"),
        "title_line1": line1, "title_line2": line2,
        "p1": points[0], "p2": points[1], "p3": points[2],
        "p4": points[3], "p5": points[4],
    }
    tpl_idx = datetime.now(IST).hour % len(TEMPLATES)
    html = TEMPLATES[tpl_idx](data)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        img = _screenshot_html(page, html)
        browser.close()
    return [img], tpl_idx

def render_carousel(content_data):
    """5 images = 1 cover (the one tip) + 4 detail slides expanding that same tip."""
    total = 1 + CAROUSEL_DETAIL_SLIDES
    line1, line2 = _split_title(content_data["tip"])
    slides = content_data["slides"]

    images = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        page = browser.new_page(viewport={"width": 1080, "height": 1080})

        cover = CAROUSEL_COVER.format(
            category=content_data.get("category", "DIGITAL MARKETING"),
            title_line1=line1, title_line2=line2,
            counter=f"01 / {total:02d}",
        )
        images.append(_screenshot_html(page, cover))
        print("  [carousel] cover rendered")

        for i, s in enumerate(slides, start=2):
            html = CAROUSEL_DETAIL.format(
                num=f"{i:02d}", counter=f"{i:02d} / {total:02d}",
                heading=s.get("heading", ""), body=s.get("body", ""),
            )
            images.append(_screenshot_html(page, html))
            print(f"  [carousel] detail slide {i} rendered")

        browser.close()
    return images

def upload_cloudinary(image_bytes, topic, idx=0):
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", topic[:25])
    result = cloudinary.uploader.upload(
        image_bytes,
        folder="social_posts",
        public_id=f"{date.today()}_{slug}_{int(time.time())}_{idx}",
        resource_type="image"
    )
    return result["secure_url"]

def upload_many(image_bytes_list, topic):
    urls = []
    for i, img in enumerate(image_bytes_list):
        url = upload_cloudinary(img, topic, idx=i)
        print(f"  [upload] {i+1}/{len(image_bytes_list)} -> {url}")
        urls.append(url)
    return urls

# ── BUFFER POSTING ───────────────────────────────────────
def post_buffer(image_urls, caption, channel_id, platform):
    """One url = normal post. Multiple urls = carousel."""
    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id status } }
        ... on MutationError { message }
      }
    }
    """
    if platform == "facebook":
        metadata = {"facebook": {"type": "post"}}
    elif platform == "instagram":
        metadata = {"instagram": {"type": "post", "shouldShareToFeed": True}}
    else:
        metadata = {}

    assets = [{"image": {"url": u}} for u in image_urls]

    variables = {
        "input": {
            "channelId": channel_id,
            "text": caption,
            "schedulingType": "automatic",
            "mode": "addToQueue",
            "assets": assets,
            "metadata": metadata
        }
    }
    resp = requests.post(
        "https://api.buffer.com/graphql",
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {BUFFER_TOKEN}", "Content-Type": "application/json"},
        timeout=60
    )
    return resp.json()

def publish_post(image_urls, caption):
    results = {}
    print("  Posting Facebook...")
    results["facebook"]  = post_buffer(image_urls, caption, BUFFER_FB_CHANNEL, "facebook")
    print("  Posting Instagram...")
    results["instagram"] = post_buffer(image_urls, caption, BUFFER_IG_CHANNEL, "instagram")
    print("  Posting LinkedIn...")
    results["linkedin"]  = post_buffer(image_urls, caption, BUFFER_LI_CHANNEL, "linkedin")
    return results

# ── POST BUILDERS ─────────────────────────────────────────
def build_single_post(topic):
    print(f"\n[single] Topic: {topic}")
    content = generate_single_content(topic)
    print(f"[single] Title: {content.get('title','')}")
    caption = f"{content['caption']}\n\n{content['hashtags']}"
    imgs, tpl_idx = render_single(content)
    urls = upload_many(imgs, topic)
    return {"type": "single", "topic": topic, "content": content,
            "images": urls, "caption": caption, "template": tpl_idx,
            "created_at": datetime.now(IST).isoformat()}

def build_carousel_post(topic):
    print(f"\n[carousel] Topic: {topic}")
    content = generate_carousel_content(topic)
    print(f"[carousel] Tip: {content.get('tip','')}")
    caption = f"{content['caption']}\n\n{content['hashtags']}"
    imgs = render_carousel(content)
    urls = upload_many(imgs, topic)
    return {"type": "carousel", "topic": topic, "content": content,
            "images": urls, "caption": caption,
            "created_at": datetime.now(IST).isoformat()}

# ── APPROVAL UI ───────────────────────────────────────────
pending = {}           # post_id -> post dict
state = {"awaiting": None}  # "carousel_topic"/"single_topic"/("edit",id)/("caption",id)/None

def approval_markup(post_id):
    return {"inline_keyboard": [
        [{"text": "✅ Approve & Post", "callback_data": f"approve_{post_id}"},
         {"text": "❌ Reject", "callback_data": f"reject_{post_id}"}],
        [{"text": "✏️ Edit Caption", "callback_data": f"edit_{post_id}"},
         {"text": "🔄 Regenerate", "callback_data": f"regen_{post_id}"}]
    ]}

def send_for_approval(post_id, post):
    pending[post_id] = post
    kind = "🖼 SINGLE" if post["type"] == "single" else f"🎠 CAROUSEL ({len(post['images'])} images, 1 tip)"
    preview = (
        f"📋 <b>Post #{post_id}</b>  &middot;  {kind}\n"
        f"📌 <b>Topic:</b> {post['topic']}\n\n"
        f"📝 <b>Caption:</b>\n{post['caption'][:400]}\n\n"
        f"👇 Tap a button below:"
    )
    if post["type"] == "carousel":
        tg_send_media_group(post["images"])
        tg_send(preview, approval_markup(post_id))
    else:
        tg_send_photo(post["images"][0], preview, approval_markup(post_id))

def send_awaiting_caption(post_id, post):
    """Built images, but NO caption yet. Show images, ask Rio for the caption.
    No Approve button until a caption arrives. No caption = never posted."""
    post["caption"] = ""
    post["awaiting_caption"] = True
    post["_ts"] = time.time()
    pending[post_id] = post
    state["awaiting"] = ("caption", post_id)
    kind = "single" if post["type"] == "single" else "carousel"
    if post["type"] == "carousel":
        tg_send_media_group(post["images"])
    else:
        tg_send_photo(post["images"][0], f"🖼 Post #{post_id} ({kind}) — images ready.")
    tg_send(
        f"✍️ <b>Send the CAPTION for post #{post_id}.</b>\n"
        f"Topic: {post['topic']}\n\n"
        f"If you don't send a caption within {MANUAL_CAPTION_EXPIRY_HOURS}h, it will NOT be posted."
    )

# ── PUBLISH ───────────────────────────────────────────────
def do_publish(post_id):
    post = pending.get(post_id)
    if not post:
        tg_send(f"⚠️ Post #{post_id} not found (maybe already handled).")
        return
    if not post.get("caption", "").strip():
        tg_send(f"⚠️ Post #{post_id} has no caption yet. Send a caption first.")
        return
    tg_send(f"⏳ Publishing post #{post_id} to FB + IG + LinkedIn...")
    try:
        results = publish_post(post["images"], post["caption"])
        tg_send("✅ Sent to Buffer queue for FB / IG / LinkedIn.")
        save_history({"post_id": post_id, "type": post["type"], "topic": post["topic"],
                      "caption": post["caption"], "images": post["images"],
                      "status": "approved", "results": results,
                      "timestamp": datetime.now(IST).isoformat()})
        del pending[post_id]
    except Exception as e:
        tg_send(f"❌ Publishing failed: {e}")

# ── CALLBACKS / MESSAGES ──────────────────────────────────
def handle_callback(cb):
    data = cb["data"]
    tg_answer_callback(cb["id"])

    if data.startswith("approve_"):
        do_publish(int(data.split("_")[1]))

    elif data.startswith("reject_"):
        post_id = int(data.split("_")[1])
        if post_id in pending:
            save_history({"post_id": post_id, "topic": pending[post_id]["topic"],
                          "status": "rejected", "timestamp": datetime.now(IST).isoformat()})
            del pending[post_id]
        tg_send(f"🗑️ Post #{post_id} rejected.")

    elif data.startswith("edit_"):
        post_id = int(data.split("_")[1])
        state["awaiting"] = ("edit", post_id)
        tg_send(f"✏️ Send the new caption for post #{post_id}:")

    elif data.startswith("regen_"):
        post_id = int(data.split("_")[1])
        old = pending.get(post_id)
        if old:
            tg_send(f"🔄 Regenerating post #{post_id}...")
            try:
                if old["type"] == "carousel":
                    new_post = build_carousel_post(old["topic"])
                else:
                    new_post = build_single_post(pick_topic())
                del pending[post_id]
                send_for_approval(post_id, new_post)
            except Exception as e:
                tg_send(f"❌ Regen failed: {e}")

def handle_message(msg):
    text = (msg.get("text") or "").strip()
    if not text:
        return

    aw = state["awaiting"]

    # Caption for an edit
    if isinstance(aw, tuple) and aw[0] == "edit":
        post_id = aw[1]; state["awaiting"] = None
        if post_id in pending:
            pending[post_id]["caption"] = text
            tg_send(f"✏️ Caption updated for post #{post_id}.", approval_markup(post_id))
        return

    # Manual caption for a built post
    if isinstance(aw, tuple) and aw[0] == "caption":
        post_id = aw[1]; state["awaiting"] = None
        if post_id in pending:
            pending[post_id]["caption"] = text
            pending[post_id]["awaiting_caption"] = False
            tg_send(f"✅ Caption set for post #{post_id}. Approve to publish:", approval_markup(post_id))
        return

    # Topic for an on-demand carousel
    if aw == "carousel_topic":
        state["awaiting"] = None
        tg_send(f"🎠 Building 1-tip carousel for: <b>{text}</b> ...")
        try:
            send_for_approval(int(time.time()) % 100000, build_carousel_post(text))
        except Exception as e:
            tg_send(f"❌ Carousel build failed: {e}")
        return

    # Topic for an on-demand single
    if aw == "single_topic":
        state["awaiting"] = None
        tg_send(f"🖼 Building single post for: <b>{text}</b> ...")
        try:
            send_for_approval(int(time.time()) % 100000, build_single_post(text))
        except Exception as e:
            tg_send(f"❌ Build failed: {e}")
        return

    # Commands
    cmd = text.lower().split()[0]
    if cmd in ("/start", "/help"):
        tg_send(
            "🤖 <b>Gundrux Bot</b>\n\n"
            "/post — auto single post (random topic) now\n"
            "/single — single post on a topic YOU type\n"
            "/carousel — 5-image, 1-tip carousel on a topic YOU type\n"
            "/help — this menu\n\n"
            f"Daily auto: {', '.join(s['time'] for s in SCHEDULE)} IST. "
            "The 6 PM slot waits for YOUR caption before it can post."
        )
    elif cmd == "/post":
        tg_send("🖼 Generating an auto single post now...")
        try:
            send_for_approval(int(time.time()) % 100000, build_single_post(pick_topic()))
        except Exception as e:
            tg_send(f"❌ Failed: {e}")
    elif cmd == "/single":
        state["awaiting"] = "single_topic"
        tg_send("🖼 Send me the topic / text for the single post:")
    elif cmd == "/carousel":
        state["awaiting"] = "carousel_topic"
        tg_send("🎠 Send me the topic. I'll make a 5-image carousel built around ONE tip:")
    else:
        # Fallback: if a manual-caption post is waiting and state was lost, treat this as its caption.
        waiting = [pid for pid, p in pending.items() if p.get("awaiting_caption")]
        if waiting:
            post_id = sorted(waiting)[-1]
            pending[post_id]["caption"] = text
            pending[post_id]["awaiting_caption"] = False
            tg_send(f"✅ Caption set for post #{post_id}. Approve to publish:", approval_markup(post_id))
        else:
            tg_send("Unknown command. Send /help to see options.")

# ── SCHEDULER ─────────────────────────────────────────────
def fire_slot(slot):
    t = slot["type"]; manual = slot["manual_caption"]
    tg_send(f"🤖 <b>Scheduled {t} post</b> &middot; {datetime.now(IST).strftime('%H:%M %d %b')} IST")
    try:
        topic = pick_topic()
        post = build_carousel_post(topic) if t == "carousel" else build_single_post(topic)
        post_id = int(time.time()) % 100000
        if manual:
            send_awaiting_caption(post_id, post)
        else:
            send_for_approval(post_id, post)
    except Exception as e:
        tg_send(f"❌ Scheduled generation failed: {e}")

def expire_stale_posts():
    now_ts = time.time()
    for pid in list(pending.keys()):
        p = pending[pid]
        if p.get("awaiting_caption") and now_ts - p.get("_ts", now_ts) > MANUAL_CAPTION_EXPIRY_HOURS * 3600:
            del pending[pid]
            if isinstance(state["awaiting"], tuple) and state["awaiting"][1] == pid:
                state["awaiting"] = None
            tg_send(f"⌛ Post #{pid} expired — no caption given, so it was NOT posted.")

# ── MAIN LOOP (always-on) ─────────────────────────────────
def main():
    print(f"Bot starting (always-on) at {datetime.now(IST)} IST")
    tg_send(
        f"🚀 <b>Gundrux Bot Online</b>\n"
        f"⏰ {datetime.now(IST).strftime('%H:%M %d %b %Y')} IST\n"
        f"📆 Auto: {', '.join(s['time'] for s in SCHEDULE)} IST "
        f"(6 PM = carousel, you supply the caption)\n"
        f"Send /help for commands."
    )

    offset = 0
    fired_today = {}

    while True:
        try:
            for update in tg_get_updates(offset, timeout=10):
                offset = update["update_id"] + 1
                if "callback_query" in update:
                    handle_callback(update["callback_query"])
                elif "message" in update:
                    handle_message(update["message"])
        except Exception as e:
            print(f"[loop] telegram error: {e}")

        try:
            now = datetime.now(IST)
            hhmm = now.strftime("%H:%M")
            today = now.strftime("%Y-%m-%d")
            for slot in SCHEDULE:
                if hhmm == slot["time"] and fired_today.get(slot["time"]) != today:
                    fired_today[slot["time"]] = today
                    print(f"[schedule] firing slot {slot['time']} ({slot['type']})")
                    fire_slot(slot)
            expire_stale_posts()
        except Exception as e:
            print(f"[loop] schedule error: {e}")

        time.sleep(1)

if __name__ == "__main__":
    main()
