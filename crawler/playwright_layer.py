"""Layer 3: Playwright Stealth — for Amazon/Flipkart (heavy anti-bot sites)."""

import json
import logging
import os
import sys
import textwrap
from typing import Optional

logger = logging.getLogger(__name__)


# Standalone script executed in a subprocess to avoid asyncio/threading
# issues with Playwright on Windows.
_STEALTH_SCRIPT = textwrap.dedent(r'''
import asyncio
import json
import random
import sys

async def _crawl(url, timeout):
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    stealth = Stealth()

    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = await context.new_page()

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=timeout * 1000,
        )

        # Human-like mouse movement
        await page.mouse.move(
            random.randint(100, 800),
            random.randint(100, 600),
            steps=random.randint(5, 15),
        )
        await asyncio.sleep(random.uniform(1.5, 3.5))

        # Scroll down slowly
        for _ in range(random.randint(2, 4)):
            await page.mouse.wheel(0, random.randint(200, 500))
            await asyncio.sleep(random.uniform(0.5, 1.5))

        await asyncio.sleep(random.uniform(1.0, 2.0))

        html = await page.content()
        await browser.close()

        if not html or len(html) < 500:
            return None

        return {
            "html": html,
            "source": "playwright_stealth",
            "url": url,
        }

url = sys.argv[1]
timeout = int(sys.argv[2])
result = asyncio.run(_crawl(url, timeout))
if result:
    print(json.dumps({"ok": True, "data": result}))
else:
    print(json.dumps({"ok": False}))
''')


def extract_with_playwright_stealth(
    url: str, timeout: int = 30
) -> Optional[dict]:
    """
    Run Playwright Stealth in a subprocess to avoid asyncio/threading
    issues on Windows.
    """
    import subprocess

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.run(
            [sys.executable, "-c", _STEALTH_SCRIPT, url, str(timeout)],
            capture_output=True,
            text=True,
            timeout=timeout + 15,
            env=env,
            encoding="utf-8",
            errors="replace",
        )

        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            if "No module named" in stderr:
                logger.error("Playwright or stealth not installed: %s", stderr[:200])
            else:
                logger.debug("Playwright stealth subprocess failed: %s", stderr[:200])
            return None

        output_lines = proc.stdout.strip().splitlines()
        if not output_lines:
            logger.debug("Playwright stealth subprocess produced no output")
            return None

        result = json.loads(output_lines[-1])
        if result.get("ok"):
            return result["data"]
        return None

    except subprocess.TimeoutExpired:
        logger.debug("Playwright stealth subprocess timed out for %s", url)
        return None
    except Exception as e:
        logger.debug("Playwright stealth sync wrapper failed: %s", e)
        return None