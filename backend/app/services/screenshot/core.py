import asyncio
import csv
import logging
from collections import Counter
from pathlib import Path

RESULT_STATUS_SUCCESS = "success"
RESULT_STATUS_FAILED = "failed"
RESULT_STATUS_SKIPPED = "skipped"
RESULT_HEADERS = ["seq", "input", "final_url", "status", "error", "screenshot_path"]


def build_candidate_urls(raw_value: str) -> list[str]:
    value = (raw_value or "").strip()
    if not value:
        return []
    if value.startswith("http://") or value.startswith("https://"):
        return [value]
    return [f"https://{value}", f"http://{value}"]


def sanitize_filename(text: str, limit: int = 120) -> str:
    cleaned = str(text or "").strip()
    for char in '<>:"/\\|?*':
        cleaned = cleaned.replace(char, "_")
    return cleaned[:limit] or "site"


def build_output_filename(seq: str, page_title: str, final_url: str) -> str:
    safe_seq = sanitize_filename(seq, limit=20)
    safe_title = sanitize_filename(page_title or "未命名", limit=80)
    safe_url = sanitize_filename(final_url, limit=160)
    return f"{safe_seq}_{safe_title}_{safe_url}.png"


def build_output_path(out_dir: Path, seq: str, page_title: str, final_url: str) -> Path:
    return out_dir / build_output_filename(seq=seq, page_title=page_title, final_url=final_url)


def build_result_row(seq: str, input_value: str, final_url: str, status: str, error: str, screenshot_path: Path) -> dict[str, str]:
    return {
        "seq": seq,
        "input": input_value,
        "final_url": final_url,
        "status": status,
        "error": error,
        "screenshot_path": str(screenshot_path),
    }


def classify_failure_reason(error: str) -> str:
    lowered = (error or "").lower()
    if "timeout" in lowered:
        return "timeout"
    if "name_not_resolved" in lowered or "err_name_not_resolved" in lowered or "connection" in lowered or "dns" in lowered:
        return "dns_or_network"
    if "ssl" in lowered or "cert" in lowered:
        return "ssl"
    return "other"


def build_summary(results: list[dict[str, str]]) -> dict[str, object]:
    total = len(results)
    success = sum(1 for item in results if item.get("status") == RESULT_STATUS_SUCCESS)
    failed = sum(1 for item in results if item.get("status") == RESULT_STATUS_FAILED)
    skipped = sum(1 for item in results if item.get("status") == RESULT_STATUS_SKIPPED)
    reasons = Counter(classify_failure_reason(item.get("error", "")) for item in results if item.get("status") == RESULT_STATUS_FAILED)
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "success_rate": f"{(success / total * 100) if total else 0:.2f}%",
        "failed_rate": f"{(failed / total * 100) if total else 0:.2f}%",
        "skipped_rate": f"{(skipped / total * 100) if total else 0:.2f}%",
        "failure_reasons": dict(reasons),
    }


def render_summary_text(summary: dict[str, object]) -> str:
    lines = [
        f"Total: {summary['total']}",
        f"Success: {summary['success']} ({summary['success_rate']})",
        f"Failed: {summary['failed']} ({summary['failed_rate']})",
        f"Skipped: {summary['skipped']} ({summary['skipped_rate']})",
        "Failure reasons:",
    ]
    failure_reasons = summary.get("failure_reasons", {})
    if failure_reasons:
        for reason, count in sorted(failure_reasons.items()):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def write_summary_text(summary_path: Path, summary_text: str) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary_text, encoding="utf-8")


def write_results_csv(results: list[dict[str, str]], result_csv: Path) -> None:
    result_csv.parent.mkdir(parents=True, exist_ok=True)
    with result_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_HEADERS)
        writer.writeheader()
        writer.writerows(results)


def finalize_screenshot_path(current_path: Path, seq: str, fallback_title: str, actual_title: str, final_url: str) -> Path:
    chosen_title = (actual_title or "").strip() or fallback_title or "未命名"
    target_path = current_path.with_name(build_output_filename(seq=seq, page_title=chosen_title, final_url=final_url))
    if target_path == current_path:
        return current_path
    if target_path.exists():
        target_path.unlink()
    current_path.replace(target_path)
    return target_path


def should_skip_existing(output_path: Path) -> bool:
    return output_path.exists()


async def capture_screenshot(page, candidate_urls: list[str], output_path: Path, timeout_sec: int, wait_after_load: int) -> dict[str, str]:
    last_error: Exception | None = None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for url in candidate_urls:
        try:
            # 增加 wait_until 内容，更激进地等待
            await page.goto(url, timeout=timeout_sec * 1000, wait_until="load")
            await asyncio.sleep(wait_after_load)

            # 在截图前检查是否真的是个有效页面
            content = await page.content()
            if len(content) < 200:
                # 页面内容过短，可能是被防火墙阻断后返回的空页面
                raise ValueError(f"Page content too short ({len(content)} bytes), likely blocked by firewall or empty response")

            await page.screenshot(path=str(output_path), full_page=False)
            return {
                "final_url": url,
                "actual_title": (await page.title()).strip(),
            }
        except Exception as exc:
            # 记录详细的异常类型
            error_msg = f"{type(exc).__name__}: {str(exc)}"
            last_error = Exception(error_msg)
    if last_error is not None:
        raise last_error
    raise ValueError("No candidate URLs generated")


async def run_one_asset(asset: dict[str, str], browser_context, semaphore: asyncio.Semaphore, out_dir: Path, timeout_sec: int, wait_after_load: int, retry_count: int, skip_existing: bool, logger: logging.Logger | None = None) -> dict[str, str]:
    async with semaphore:
        target_value = asset.get("url", "") or asset.get("host", "")
        candidates = build_candidate_urls(target_value)
        first_candidate = candidates[0] if candidates else target_value
        output_path = build_output_path(out_dir, asset.get("seq", ""), asset.get("title", ""), first_candidate)

        if skip_existing and should_skip_existing(output_path):
            result = build_result_row(asset.get("seq", ""), target_value, first_candidate, RESULT_STATUS_SKIPPED, "", output_path)
            if logger:
                logger.info("Skipped asset %s -> %s", asset.get("seq", ""), first_candidate)
            return result

        page = await browser_context.new_page()
        try:
            last_error: Exception | None = None
            for attempt in range(retry_count + 1):
                try:
                    if attempt > 0:
                        # 指数退避，重试前等待 (2, 4, 8...) 秒
                        wait_sec = 2 ** attempt
                        if logger:
                            logger.info("Retrying asset %s, attempt %d, waiting %ds", asset.get("seq", ""), attempt, wait_sec)
                        await asyncio.sleep(wait_sec)

                    capture_result = await capture_screenshot(page, candidates, output_path, timeout_sec, wait_after_load)
                    final_url = capture_result.get("final_url", first_candidate)
                    actual_title = capture_result.get("actual_title", "")
                    final_path = finalize_screenshot_path(
                        current_path=output_path,
                        seq=asset.get("seq", ""),
                        fallback_title=asset.get("title", ""),
                        actual_title=actual_title,
                        final_url=final_url,
                    )
                    result = build_result_row(asset.get("seq", ""), target_value, final_url, RESULT_STATUS_SUCCESS, "", final_path)
                    if logger:
                        logger.info("Captured asset %s -> %s", asset.get("seq", ""), final_url)
                    return result
                except Exception as exc:
                    last_error = exc
            result = build_result_row(
                asset.get("seq", ""),
                target_value,
                first_candidate,
                RESULT_STATUS_FAILED,
                str(last_error) if last_error else "Unknown error",
                output_path,
            )
            if logger:
                logger.error("Failed asset %s -> %s: %s", asset.get("seq", ""), first_candidate, result["error"])
            return result
        finally:
            await page.close()


async def run_batch(assets: list[dict[str, str]], out_dir: Path, timeout_sec: int, wait_after_load: int, concurrency: int, retry_count: int, skip_existing: bool, headful: bool, logger: logging.Logger | None = None) -> list[dict[str, str]]:
    from playwright.async_api import async_playwright

    semaphore = asyncio.Semaphore(max(1, concurrency))
    out_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        # 增加启动参数以支持老旧 TLS 协议和指纹伪装
        browser = await playwright.chromium.launch(
            headless=not headful,
            args=[
                "--disable-web-security",
                "--allow-running-insecure-content",
                "--ignore-certificate-errors",
                "--ssl-version-min=tls1",          # 强行支持 TLS 1.0 (兼容老旧政企系统)
                "--disable-blink-features=AutomationControlled" # 隐藏自动化特征
            ]
        )
        # 伪装真实的 User-Agent
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            ignore_https_errors=True,
            user_agent=user_agent
        )

        # 注入脚本移除自动化特征
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        try:
            tasks = [
                run_one_asset(asset, context, semaphore, out_dir, timeout_sec, wait_after_load, retry_count, skip_existing, logger)
                for asset in assets
            ]
            results = await asyncio.gather(*tasks)
        finally:
            await context.close()
            await browser.close()
    return sorted(results, key=lambda item: (int(item["seq"]) if str(item.get("seq", "")).isdigit() else 0, item.get("seq", "")))
