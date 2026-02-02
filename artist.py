import logging
import asyncio
import time
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

logger = logging.getLogger("Artist")

class RateLimiter:
    def __init__(self, rate=15, per=60.0): # 15 images per minute
        self.rate = rate
        self.per = per
        self.allowance = rate
        self.last_check = time.time()

    def can_proceed(self):
        current = time.time()
        time_passed = current - self.last_check
        self.last_check = current
        self.allowance += time_passed * (self.rate / self.per)
        if self.allowance > self.rate:
            self.allowance = self.rate
        
        if self.allowance < 1.0:
            return False
        
        self.allowance -= 1.0
        return True

class Artist:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.limiter = RateLimiter()
        
        # Load assets
        try:
            self.bg_layer = Image.open('background.png').convert('RGB')
            # Ensure it's the right size, or resize it? Better to enforce spec or resize safe.
            if self.bg_layer.size != (1000, 300):
                logger.warning(f"background.png size mismatch {self.bg_layer.size}. Resizing to 1000x300.")
                self.bg_layer = self.bg_layer.resize((1000, 300))
            logger.info("Loaded custom background.png")
        except FileNotFoundError:
            logger.warning("background.png not found. Using procedural placeholder.")
            self.bg_layer = self._create_placeholder_bg()
        
    def _create_placeholder_bg(self):
        # Create a dark medieval/cyberpunk background
        img = Image.new('RGB', (1000, 300), color=(25, 20, 30))
        d = ImageDraw.Draw(img)
        # Add some texture/noise lines
        for i in range(0, 1000, 20):
            d.line([(i, 0), (i+10, 300)], fill=(35, 30, 40), width=2)
        d.rectangle([0,0, 1000, 300], outline=(60,50,40), width=5)
        return img

    async def generate_ai_image(self, prompt):
        if not self.limiter.can_proceed():
            logger.warning("Rate limit hit, using fallback.")
            return None

        try:
             logger.info(f"Generating image for prompt: {prompt}")
             response = await asyncio.to_thread(
                 self.client.models.generate_images,
                 model='gemini-2.0-flash', 
                 prompt=prompt,
                 config=types.GenerateImagesConfig(
                     number_of_images=1,
                     aspect_ratio="1:1"
                 )
             )
             
             if response.generated_images:
                 image_bytes = response.generated_images[0].image.image_bytes
                 return Image.open(BytesIO(image_bytes))
             
        except Exception as e:
            logger.error(f"Image Gen Error: {e}")
        
        return None

    def composite(self, ai_image, text_data):
        # Canvas: 1000x300
        canvas = self.bg_layer.copy()
        
        # Process AI Image
        if ai_image:
            ai_image = ai_image.resize((290, 290))
            # Paste with simple margin
            canvas.paste(ai_image, (5, 5)) 
        else:
             # Draw fallback placeholder
             d = ImageDraw.Draw(canvas)
             d.rectangle([5,5,295,295], fill=(50,20,20))
             d.text((100, 140), "NO SIGNAL", fill=(200, 200, 200))
        
        # Text Rendering
        d = ImageDraw.Draw(canvas)
        
        def load_font(size):
            try:
                # Try a standard font that usually exists or fallback
                return ImageFont.truetype("arial.ttf", size)
            except:
                return ImageFont.load_default()

        name_font = load_font(60)
        title_font = load_font(40)
        detail_font = load_font(25)

        # Positioning
        text_x = 320
        
        # Rank/Title (White)
        d.text((text_x, 20), text_data.get('title', 'Unknown Title'), font=title_font, fill=(220, 220, 220))
        
        # Name (Gold)
        # Check if title pushed it down? No, fixed layout.
        d.text((text_x, 70), text_data.get('name', 'Unknown Character'), font=name_font, fill=(255, 215, 0))
        
        # Date/Activity
        d.text((text_x, 150), f"Year: {text_data.get('date', 'Unknown')}", font=detail_font, fill=(150, 150, 150))
        d.text((text_x, 190), f"Status: {text_data.get('status', 'Idle')}", font=detail_font, fill=(150, 150, 150))
        
        # Lifestyle (if available) - just append to status or new line
        lifestyle = text_data.get('lifestyle')
        if lifestyle:
            d.text((text_x, 230), f"Lifestyle: {lifestyle}", font=detail_font, fill=(150, 150, 150))

        output = BytesIO()
        canvas.save(output, format='PNG')
        output.seek(0)
        return output
