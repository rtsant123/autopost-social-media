import os
import time
import json
import random
import requests
import cloudinary
import cloudinary.uploader
from datetime import date
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import anthropic
from replicate.client import Client as ReplicateClient

# CONFIG
REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]
CLOUDINARY_CLOUD    = os.environ["CLOUDINARY_CLOUD"]
CLOUDINARY_KEY      = os.environ["CLOUDINARY_API_KEY"]
CLOUDINARY_SECRET   = os.environ["CLOUDINARY_SECRET"]
FB_PAGE_ID          = os.environ["FB_PAGE_ID"]
FB_ACCESS_TOKEN     = os.environ["FB_ACCESS_TOKEN"]
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
LOGO_URL            = os.environ.get("LOGO_URL", "")

# CLOUDINARY SETUP
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD,
    api_key=CLOUDINARY_KEY,
    api_secret=CLOUDINARY_SECRET
)

# DEFAULT TOPICS
DEFAULT_TOPICS = [
    "SEO tips for small businesses in 2025",
    "WordPress speed optimization guide",
    "Social media content strategy for brands",
    "Google ranking factors you must know",
    "On-page SEO checklist for beginners",
    "WordPress plugins every business needs",
    "Instagram growth tips for digital agencies",
    "Local SEO strategies that actually work",
    "Content marketing for B2B companies",
    "Technical SEO basics explained",
    "Link building strategies for 2025",
    "How to do keyword research properly",
    "WordPress security best practices",
    "Email marketing vs social media marketing",
    "Why your website is not ranking on Google",
    "How to write SEO-friendly blog posts",
    "Best tools for social media management",
    "Mobile SEO optimization tips",
    "How to use AI for content creation",
    "Common WordPress mistakes to avoid",
    "Schema markup for better SEO",
    "How to grow a brand on Instagram",
    "Core Web Vitals explained simply",
    "Backlink audit step by step guide",
    "Social proof strategies for businesses",
    "How to do competitor SEO analysis",
    "WordPress vs custom website for SEO",
    "Voice search optimization tips",
    "How to write meta descriptions that get clicks",
    "Video SEO for YouTube and Google",
]

CUSTOM_TOPICS_FILE = "custom_topics.txt"


def load_topics():
    topics = DEFAULT_TOPICS.copy()
    if os.path.exists(CUSTOM_TOPICS_FILE):
        with open(CUSTOM_TOPICS_FILE, "r") as f:
            custom = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            topics.extend(custom)
            print(f"Loaded {len(custom)} custom topics")
    return topics


def get_todays_topics(count=6):
    topics = load_topics()
    seed = int(date.today().strftime("%Y%m%d"))
    random.seed(seed)
    return random.sample(topics, min(count, len(topics)))


def generate_caption_and_prompt(topic):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    f"You are a social media expert for Gundrux, a digital marketing agency "
                    f"specializing in SEO, WordPress, and social media growth.\n\n"
                    f"Topic: {topic}\n\n"
                    f"Return pure JSON only (no markdown, no explanation) with these keys:\n"
                    f"1. caption: 2-3 engaging lines for Facebook post\n"
                    f"2. image_prompt: detailed prompt for AI image. Style: professional "
                    f"infographic, dark navy blue background, white and gold text, clean modern "
                    f"design, bold typography, no people, no faces, business/tech visual\n"
                    f"3. hashtags: 15 relevant hashtags as single string\n\n"
                    f"Pure JSON only."
                )
            }
        ]
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def generate_image(image_prompt):
    client = ReplicateClient(api_token=REPLICATE_API_TOKEN)
    output = client.run(
        "black-forest-labs/flux-schnell",
        input={
            "prompt": image_prompt,
            "num_outputs": 1,
            "aspect_ratio": "1:1",
            "output_format": "jpg",
            "output_quality": 90
        }
    )
    image_url = str(output[0])
    return requests.get(image_url).content


def add_watermark(image_bytes):
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")

    if LOGO_URL:
        try:
            logo_resp = requests.get(LOGO_URL, timeout=10)
            logo = Image.open(BytesIO(logo_resp.content)).convert("RGBA")
            logo_w = int(img.width * 0.15)
            ratio = logo_w / logo.width
            logo_h = int(logo.height * ratio)
            logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
            r, g, b, a = logo.split()
            a = a.point(lambda x: int(x * 0.85))
            logo.putalpha(a)
            x = img.width - logo_w - 20
            y = img.height - logo_h - 20
            img.paste(logo, (x, y), logo)
            print("Logo added")
        except Exception as e:
            print(f"Logo failed, using text: {e}")
            img = add_text_watermark(img)
    else:
        img = add_text_watermark(img)

    final = Image.new("RGB", img.size, (255, 255, 255))
    final.paste(img, mask=img.split()[3])
    out = BytesIO()
    final.save(out, format="JPEG", quality=92)
    return out.getvalue()


def add_text_watermark(img):
    draw = ImageDraw.Draw(img)
    text = "gundrux.in"
    font_size = int(img.width * 0.032)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = img.width - tw - 20
    y = img.height - th - 20
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 150))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 210))
    return img


def upload_to_cloudinary(image_bytes, topic):
    slug = topic[:25].replace(" ", "_").replace("/", "-")
    result = cloudinary.uploader.upload(
        image_bytes,
        folder="facebook_posts",
        public_id=f"{date.today()}_{slug}",
        resource_type="image"
    )
    return result["secure_url"]


def post_to_facebook(image_url, caption):
    result = requests.post(
        f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos",
        data={
            "url": image_url,
            "message": caption,
            "access_token": FB_ACCESS_TOKEN
        }
    ).json()
    print(f"Facebook result: {result}")
    if "id" not in result:
        raise Exception(f"Failed: {result}")
    return result


def run_single_post(topic):
    print(f"\nTopic: {topic}")

    print("Generating caption + image prompt (Claude Haiku)...")
    content = generate_caption_and_prompt(topic)
    caption = f"{content['caption']}\n\n{content['hashtags']}"

    print("Generating image (Flux)...")
    image_bytes = generate_image(content["image_prompt"])

    print("Adding watermark...")
    image_bytes = add_watermark(image_bytes)

    print("Uploading to Cloudinary...")
    url = upload_to_cloudinary(image_bytes, topic)
    print(f"Image URL: {url}")

    print("Posting to Facebook...")
    result = post_to_facebook(url, caption)
    print(f"Done: {result}")


def run_daily_posts(count=6):
    topics = get_todays_topics(count)
    interval = (14 * 3600) // count

    print(f"\nToday: {date.today()}")
    print(f"{count} topics queued:")
    for i, t in enumerate(topics):
        print(f"  {i+1}. {t}")

    for i, topic in enumerate(topics):
        try:
            run_single_post(topic)
        except Exception as e:
            print(f"Post {i+1} failed: {e}")

        if i < len(topics) - 1:
            mins = interval // 60
            print(f"\nNext post in {mins} minutes...")
            time.sleep(interval)

    print("\nAll done for today!")


if __name__ == "__main__":
    run_daily_posts(count=6)
