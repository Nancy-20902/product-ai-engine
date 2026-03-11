"""Layer 1: Crawl4AI — AI-powered extraction (handles JS, JSON-LD, script tags)."""

import asyncio
import json
import logging
import os
import sys
import textwrap
from typing import Optional

logger = logging.getLogger(__name__)


# Standalone script executed in a subprocess to avoid asyncio/threading
# issues with Playwright on Windows.
_CRAWL_SCRIPT = textwrap.dedent(r'''
import asyncio
import json
import sys

async def _crawl(url, timeout):
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    browser_config = BrowserConfig(
        headless=True,
        extra_args=["--disable-gpu", "--no-sandbox"],
    )
    crawl_config = CrawlerRunConfig(
        wait_until="networkidle",
        page_timeout=timeout * 1000,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url, config=crawl_config)
        if not result or not result.success:
            return None
        return {
            "html": result.html,
            "markdown": getattr(result, "markdown", ""),
            "source": "crawl4ai",
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


def run_crawl4ai(url: str, timeout: int = 30) -> Optional[dict]:
    """
    Run Crawl4AI in a subprocess to avoid asyncio/threading issues
    with Playwright on Windows (Streamlit runs handlers in threads).
    """
    import subprocess

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.run(
            [sys.executable, "-c", _CRAWL_SCRIPT, url, str(timeout)],
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
                logger.error(
                    "crawl4ai not installed. "
                    "Run: pip install crawl4ai && crawl4ai-setup"
                )
            else:
                logger.debug("Crawl4AI subprocess failed: %s", stderr[:200])
            return None

        # Parse the JSON output from the last line of stdout
        output_lines = proc.stdout.strip().splitlines()
        if not output_lines:
            logger.debug("Crawl4AI subprocess produced no output")
            return None

        result = json.loads(output_lines[-1])
        if result.get("ok"):
            return result["data"]
        return None

    except subprocess.TimeoutExpired:
        logger.debug("Crawl4AI subprocess timed out for %s", url)
        return None
    except Exception as e:
        logger.debug("Crawl4AI sync wrapper failed: %s", e)
        return None