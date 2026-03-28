import asyncio
import os
import httpx
import datetime
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# --- 1. PATH CONFIGURATION ---
# Detect the directory where the script is located
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
LOGS_DIR = BASE_DIR / "logs"

# Ensure the logs directory exists
LOGS_DIR.mkdir(exist_ok=True)

# Load configuration from .env file using absolute path
load_dotenv(dotenv_path=ENV_PATH)

# Environment variables
LOGIN = os.getenv("ENEL_LOGIN")
PASSWORD = os.getenv("ENEL_PASSWORD")
CITY = os.getenv("ENEL_CITY")
CATEGORY = os.getenv("ENEL_CATEGORY")
SERVICE = os.getenv("ENEL_SERVICE")
WA_PHONE = os.getenv("WHATSAPP_PHONE")
WA_KEY = os.getenv("WHATSAPP_API_KEY")

async def send_whatsapp(message):
    """Sends a notification via CallMeBot"""
    url = f"https://api.callmebot.com/whatsapp.php?phone={WA_PHONE}&text={message}&apikey={WA_KEY}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                print(f"[{datetime.datetime.now()}] SUCCESS: WhatsApp notification sent.")
            else:
                print(f"[{datetime.datetime.now()}] ERROR: WhatsApp API returned status {response.status_code}")
        except Exception as e:
            print(f"[{datetime.datetime.now()}] EXCEPTION: Failed to connect to WhatsApp API: {e}")

async def run():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n--- SESSION STARTED: {now} ---")
    
    async with async_playwright() as p:
        print("INFO: Launching browser (HEADLESS)...")
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        page.set_default_timeout(60000)

        try:
            # 2. LOGIN AND COOKIE HANDLING
            print("INFO: Connecting to Enel-med...")
            await page.goto("https://online.enel.pl/Account/Login")

            print("INFO: Handling cookie consent...")
            try:
                cookie_btn = page.locator("#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll")
                await cookie_btn.wait_for(state="visible", timeout=7000)
                await cookie_btn.click()
                print("SUCCESS: Cookies accepted.")
            except:
                # Force remove cookie overlay if button not found
                await page.evaluate('document.getElementById("CybotCookiebotDialog")?.remove()')

            print("INFO: Authenticating...")
            await page.wait_for_selector('#Login', state="visible")
            await page.fill('#Login', LOGIN)
            await page.click('button:has-text("Potwierdź")') 
            
            await page.wait_for_selector('#Password', state="visible")
            await page.fill('#Password', PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle")
            print("SUCCESS: Logged in.")

            # 3. SEARCH CONFIGURATION
            print("INFO: Navigating to appointment search...")
            await page.goto("https://online.enel.pl/Visit/New")
            await page.wait_for_load_state("networkidle")

            async def select2_fill(label_text, value):
                print(f"INFO: Selecting {label_text}: {value}...")
                container = f"//label[contains(text(), '{label_text}')]/..//span[contains(@class, 'select2-selection--single')]"
                await page.locator(container).first.click()
                await page.wait_for_timeout(800)
                option = f"//li[contains(@class, 'select2-results__option') and contains(text(), '{value}')]"
                try:
                    await page.locator(option).last.click(timeout=5000)
                except:
                    await page.keyboard.type(value, delay=100)
                    await page.wait_for_timeout(1000)
                    await page.keyboard.press("Enter")
                await page.wait_for_timeout(1500)

            # Updated field labels for English context (using City/Category/Service)
            await select2_fill("Miasto", CITY)
            await select2_fill("Kategoria", CATEGORY)
            await page.wait_for_timeout(1000)
            await select2_fill("Usługa", SERVICE)

            # 4. CONFIRMATION AND SEARCH
            print("INFO: Confirming instructions...")
            confirm_btn = page.locator("#btn-instruction-confirm")
            await confirm_btn.wait_for(state="visible", timeout=10000)
            await confirm_btn.click()
            
            print("INFO: Executing search...")
            await page.locator("#submit").click()
            await page.wait_for_load_state("networkidle")

            # 5. RESULTS CHECKING
            count_locator = page.locator(".found-visit-count .count")
            
            try:
                await count_locator.wait_for(state="visible", timeout=15000)
                count_text = await count_locator.inner_text()
                count = int(count_text.strip())
                
                if count > 0:
                    alert_msg = f"ALERT: Found {count} slots for {SERVICE} in {CITY}!"
                    print(f"[{datetime.datetime.now()}] {alert_msg}")
                    await send_whatsapp(alert_msg)
                    # Beep sound (works only in active terminal)
                    for _ in range(3): print('\a')
                else:
                    print(f"INFO: No slots found (Count: {count}).")

            except Exception as e:
                print(f"WARNING: Count indicator not found (Likely 0 results): {e}")
                await page.screenshot(path=str(LOGS_DIR / "debug_headless.png"))

        except Exception as e:
            print(f"CRITICAL ERROR: {e}")
            await page.screenshot(path=str(LOGS_DIR / "fatal_error.png"))

        await browser.close()
        print(f"--- SESSION ENDED: {datetime.datetime.now().strftime('%H:%M:%S')} ---")

if __name__ == "__main__":
    asyncio.run(run())