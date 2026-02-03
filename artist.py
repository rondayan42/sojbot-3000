import logging
import asyncio
import time
import io 
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageOps
import google.genai as genai 
from google.genai import types 

logger = logging.getLogger("Artist")

class RateLimiter:
    """Simple rate limiter: max_calls per period (seconds)"""
    def __init__(self, rate=15, per=60):
        self.rate = rate
        self.per = per
        self.allowance = rate
        self.last_check = time.time()

    def check(self):
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
        # Configure Gemini
        # gemini-3-pro-image-preview is typically on v1beta or v1alpha
        self.client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'}) 
        self.limiter = RateLimiter(rate=5, per=60) 
        # Load assets
        try:
            self.bg_layer = PILImage.open('background.png').convert('RGB')
            logger.info("Loaded custom background.png")
        except FileNotFoundError:
            logger.warning("background.png not found. Creating placeholder.") 
            self.bg_layer = PILImage.new('RGB', (1000, 300), color=(50, 50, 50)) 

    async def generate_ai_image(self, prompt):
        if not self.limiter.check(): 
            logger.warning("Rate limit hit for AI generation.") 
            return None

        try:
            logger.info(f"Generating image with Nano Banana Pro for prompt: {prompt}")
            
            # Using synchronous call in executor to avoid blocking loop
            loop = asyncio.get_running_loop()
            
            def _generate():
                # Correct API usage for Nano Banana (multimodal generation)
                # We do NOT pass a config with response_mime_type="image/jpeg" because 
                # that triggers a text-generation validation error.
                return self.client.models.generate_content(
                    model='gemini-3-pro-image-preview', 
                    contents=[prompt + " Aspect Ratio: Wide/Landscape."]
                )

            response = await loop.run_in_executor(None, _generate)
            
            # Extract image from parts and ENSURE PIL Image
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data is not None:
                        # Convert to PIL Image immediately
                        return PILImage.open(io.BytesIO(part.inline_data.data))
                    elif part.text:
                        logger.info(f"AI returned text instead of image: {part.text}")

            logger.error("No image data found in response parts.")
            return None
             
        except Exception as e:
            logger.error(f"Image Gen Error: {e}")
            return None 

    def composite(self, ai_image, text_data):
        # Background Size: 1020x300
        canvas = self.bg_layer.copy()
        
        # --- LEFT FRAME: PORTRAIT ---
        # Refined Guess for Left Box: 
        #   x: 65, y: 70
        #   w: 290, h: 190 (User Specified)
        
        box_x, box_y = 65, 55 
        box_w, box_h = 290, 190 
        
        if ai_image:
            # Use ImageOps.fit to resize and CROP to exact dimensions without stretching
            # Centering (0.5, 0.5) usually works best for portraits
            ai_image = ImageOps.fit(ai_image, (box_w, box_h), method=PILImage.Resampling.LANCZOS, centering=(0.5, 0.5))
            canvas.paste(ai_image, (box_x, box_y)) 
        else:
             # Draw fallback placeholder
             d = ImageDraw.Draw(canvas)
             d.rectangle([box_x, box_y, box_x+box_w, box_y+box_h], fill=(20,10,10))
             d.text((box_x+80, box_y+80), "NO SIGNAL", fill=(100, 100, 100))
        
        # --- RIGHT PANEL: SCROLLS ---
        d = ImageDraw.Draw(canvas)
        
        def load_custom_font(font_path, size):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception as e:
                logger.warning(f"Could not load {font_path}: {e}. Falling back to default.")
                return ImageFont.load_default()

        # Fonts
        text_font = "MiddleAgesDeco_PERSONAL_USE.ttf"
        num_font = "TaylorGothic.otf"

        # Top Scroll (Activity + Name)
        row1_font = load_custom_font(text_font, 20)  
        # Middle Scroll (Rank)
        row2_font = load_custom_font(text_font, 30) 
        # Bottom Scroll (Date)
        row3_font = load_custom_font(num_font, 24) 

        # Coordinates for Text Centers
        # Scroll 1 (Top): "Ruling as Mordechai..."
        d.text((730, 75), text_data.get('row1', ''), font=row1_font, fill=(40, 30, 10), anchor="mm")
        
        # Scroll 2 (Middle): "Count"
        d.text((735, 160), text_data.get('row2', ''), font=row2_font, fill=(0, 0, 0), anchor="mm")
        
        # Scroll 3 (Bottom): "867"
        d.text((735, 245), text_data.get('row3', ''), font=row3_font, fill=(60, 40, 20), anchor="mm")

        output = io.BytesIO()
        canvas.save(output, format='PNG')
        output.seek(0)
        return output
