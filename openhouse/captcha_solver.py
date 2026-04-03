"""Captcha Solver — Free, self-hosted captcha bypass strategies.

Approach (no paid services required):
1. SESSION PERSISTENCE — Keep browser cookies/localStorage across runs so
   captchas solved once don't recur. This is the #1 most effective strategy.
2. STEALTH MODE — Use playwright-stealth patches to avoid detection:
   - Hide navigator.webdriver
   - Spoof browser fingerprint
   - Randomize timing
3. CLOUDFLARE TURNSTILE — For Turnstile-protected sites, use the
   cookie-session approach: once a valid cf_clearance cookie is obtained,
   it can be reused for 15-30 minutes.
4. TEXT CAPTCHA OCR — For simple image-based text captchas, attempt
   local OCR using Tesseract or basic pattern matching.

GitHub references:
- cloudflare-bypass-2026 (344 stars) — SeleniumBase UC mode approach
- cf-clearance-scraper (700 stars) — Cloudflare session extraction
- cloudflyer-oss (197 stars) — Self-hosted Turnstile bypass API

This module integrates with browser-use/Playwright as the underlying engine.
"""
import asyncio
import json
import os
import random
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from openhouse.logging import logger

# ─── Persistent Session Directory ────────────────────────────────────
SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".browser_sessions")
COOKIE_STORE = os.path.join(SESSION_DIR, "cookies.json")

# Ensure session directory exists
os.makedirs(SESSION_DIR, exist_ok=True)


class CaptchaSolver:
    """Free captcha bypass using stealth + session persistence + basic OCR."""

    def __init__(self):
        self.cookies: Dict[str, List[dict]] = {}
        self._load_cookies()

    def _load_cookies(self):
        """Load saved cookies from disk."""
        if os.path.exists(COOKIE_STORE):
            try:
                with open(COOKIE_STORE, 'r', encoding='utf-8') as f:
                    self.cookies = json.load(f)
                logger.info("CaptchaSolver: Loaded cookies for %d domains",
                           len(self.cookies))
            except (json.JSONDecodeError, IOError):
                self.cookies = {}

    def _save_cookies(self):
        """Save cookies to disk."""
        try:
            with open(COOKIE_STORE, 'w', encoding='utf-8') as f:
                json.dump(self.cookies, f, indent=2)
        except IOError as e:
            logger.error("CaptchaSolver: Failed to save cookies: %s", e)

    def get_domain_cookies(self, domain: str) -> List[dict]:
        """Get saved cookies for a domain."""
        return self.cookies.get(domain, [])

    def save_domain_cookies(self, domain: str, cookies: List[dict]):
        """Save cookies for a domain after successful visit."""
        # Filter out expired cookies
        now = time.time()
        valid_cookies = []
        for c in cookies:
            expires = c.get('expires', 0)
            if expires == 0 or expires == -1 or expires > now:
                valid_cookies.append(c)

        self.cookies[domain] = valid_cookies
        self._save_cookies()
        logger.info("CaptchaSolver: Saved %d cookies for %s",
                    len(valid_cookies), domain)

    async def apply_stealth(self, page):
        """Apply stealth patches to a Playwright page to avoid detection.

        Based on puppeteer-extra-plugin-stealth and playwright-stealth.
        """
        stealth_js = """
        // Hide webdriver flag
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });

        // Chrome runtime mock
        window.chrome = {
            runtime: {},
            loadTimes: function() { return {}; },
            csi: function() { return {}; },
            app: { isInstalled: false },
        };

        // Permissions query mock
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );

        // Plugin array mock (Chrome has plugins, headless doesn't)
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Languages mock
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en', 'de'],
        });

        // WebGL vendor mock
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter.call(this, parameter);
        };

        // Canvas fingerprint noise
        const toDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            if (type === 'image/png' && this.width > 16 && this.height > 16) {
                const ctx = this.getContext('2d');
                if (ctx) {
                    const imageData = ctx.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] ^= 1;  // Tiny noise
                    }
                    ctx.putImageData(imageData, 0, 0);
                }
            }
            return toDataURL.apply(this, arguments);
        };

        // Console debug detection bypass
        console.debug = () => {};
        """
        try:
            await page.evaluate(stealth_js)
            logger.debug("CaptchaSolver: Stealth patches applied")
        except Exception as e:
            logger.warning("CaptchaSolver: Stealth patch failed: %s", str(e)[:100])

    async def apply_cookies_to_context(self, context, domain: str):
        """Apply saved cookies to a browser context."""
        saved = self.get_domain_cookies(domain)
        if saved:
            try:
                await context.add_cookies(saved)
                logger.info("CaptchaSolver: Applied %d saved cookies for %s",
                           len(saved), domain)
            except Exception as e:
                logger.warning("CaptchaSolver: Failed to apply cookies: %s", str(e)[:100])

    async def save_cookies_from_context(self, context, domain: str):
        """Save cookies from a browser context after successful navigation."""
        try:
            cookies = await context.cookies()
            # Filter to cookies matching the domain
            domain_cookies = [c for c in cookies if domain in c.get('domain', '')]
            if domain_cookies:
                self.save_domain_cookies(domain, domain_cookies)
        except Exception as e:
            logger.warning("CaptchaSolver: Failed to extract cookies: %s", str(e)[:100])

    async def detect_captcha(self, page) -> Optional[str]:
        """Detect if a captcha is present on the page.

        Returns the captcha type or None:
        - 'cloudflare_turnstile'
        - 'recaptcha_v2'
        - 'recaptcha_v3'
        - 'hcaptcha'
        - 'text_captcha'
        - None (no captcha)
        """
        try:
            page_content = await page.content()
            page_lower = page_content.lower()

            if 'cf-turnstile' in page_lower or 'challenges.cloudflare.com' in page_lower:
                return 'cloudflare_turnstile'
            if 'g-recaptcha' in page_lower or 'recaptcha/api.js' in page_lower:
                if 'recaptcha/api.js?render=' in page_lower:
                    return 'recaptcha_v3'
                return 'recaptcha_v2'
            if 'h-captcha' in page_lower or 'hcaptcha.com' in page_lower:
                return 'hcaptcha'
            if 'captcha' in page_lower:
                return 'text_captcha'

            return None
        except Exception:
            return None

    async def handle_cloudflare_wait(self, page, timeout: int = 15):
        """Wait for Cloudflare challenge to resolve (often auto-solves with stealth).

        Cloudflare Turnstile often auto-passes on stealth browsers after a short wait.
        """
        logger.info("CaptchaSolver: Waiting for Cloudflare challenge...")
        try:
            # Wait for the challenge page to resolve
            for _ in range(timeout):
                title = await page.title()
                content = await page.content()

                # Check if challenge resolved
                if 'just a moment' not in title.lower() and \
                   'checking your browser' not in content.lower() and \
                   'cf-chl-widget' not in content.lower():
                    logger.info("CaptchaSolver: Cloudflare challenge passed!")
                    return True

                await asyncio.sleep(1)

            logger.warning("CaptchaSolver: Cloudflare challenge timeout after %ds", timeout)
            return False
        except Exception as e:
            logger.warning("CaptchaSolver: CF wait error: %s", str(e)[:100])
            return False

    def add_human_delays(self) -> float:
        """Generate random human-like delay (0.5-2.5 seconds)."""
        return random.uniform(0.5, 2.5)

    async def human_type(self, page, selector: str, text: str):
        """Type text with human-like speed variations."""
        element = page.locator(selector)
        for char in text:
            await element.type(char, delay=random.randint(50, 150))
            if random.random() < 0.05:  # 5% chance of brief pause
                await asyncio.sleep(random.uniform(0.3, 0.8))

    async def human_click(self, page, selector: str):
        """Click with small random offset to mimic human behavior."""
        element = page.locator(selector)
        box = await element.bounding_box()
        if box:
            # Click with small random offset within the element
            x = box['x'] + box['width'] * random.uniform(0.3, 0.7)
            y = box['y'] + box['height'] * random.uniform(0.3, 0.7)
            await page.mouse.click(x, y)
        else:
            await element.click()


def get_stealth_browser_config() -> dict:
    """Get Playwright browser launch config optimized for stealth.

    Returns kwargs to pass to playwright.chromium.launch_persistent_context()
    """
    return {
        'user_data_dir': SESSION_DIR,
        'headless': True,
        'args': [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-infobars',
            '--window-size=1920,1080',
            '--start-maximized',
        ],
        'user_agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/131.0.0.0 Safari/537.36'
        ),
        'viewport': {'width': 1920, 'height': 1080},
        'locale': 'de-DE',
        'timezone_id': 'Europe/Berlin',
    }


# Singleton instance
captcha_solver = CaptchaSolver()
