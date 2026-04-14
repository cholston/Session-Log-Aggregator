import os
import time
from playwright.sync_api import sync_playwright, Page


def _login_and_load(page: Page, url: str, username: str, password: str) -> bool:
    """Log in to FoundryVTT and wait for the game canvas to load.
    Returns True on success, False if the user was not found."""
    print("Navigating to login page...")
    page.goto(url)

    print("Waiting for login form...")
    page.wait_for_selector("select[name='userid']")

    user_id = page.evaluate(f"""() => {{
        const options = Array.from(document.querySelectorAll("select[name='userid'] option"));
        const userOption = options.find(opt => opt.textContent.trim() === '{username}');
        return userOption ? userOption.value : null;
    }}""")

    if not user_id:
        print(f"Error: User '{username}' not found in the login dropdown.")
        return False

    page.select_option("select[name='userid']", user_id)

    if password:
        page.fill("input[name='password']", password)

    print("Joining game...")
    page.click("button[name='join']")

    print("Waiting for game canvas to load...")
    page.wait_for_selector("#board", timeout=60000)
    time.sleep(2)
    return True


def _click_chat_tab(page: Page):
    """Ensure the chat sidebar tab is active."""
    for selector in ["button[data-tab='chat']", "a.item[data-tab='chat']", "[data-tab='chat']"]:
        locator = page.locator(selector).first
        if locator.is_visible():
            print(f"Found chat tab using selector: {selector}")
            locator.click()
            time.sleep(1)
            return


def _trigger_macro_slot(page: Page, slot: int) -> str | None:
    """Click a macro hotbar slot and intercept the resulting file download.
    Returns the save path, or None if no download occurred within the timeout."""
    macro_selectors = [
        f"#hotbar [data-slot='{slot}']",
        f"#hotbar .macro[data-slot='{slot}']",
        f".macro[data-slot='{slot}']",
        f"[data-macro-slot='{slot}']",
        f"[data-slot='{slot}']",
    ]

    macro_btn = None
    for selector in macro_selectors:
        locator = page.locator(selector).first
        if locator.is_visible():
            macro_btn = locator
            print(f"Found macro slot {slot} using selector: {selector}")
            break

    if not macro_btn:
        print(f"Error: Could not find macro hotbar slot {slot}.")
        return None

    print(f"Executing macro in slot {slot}...")
    try:
        with page.expect_download(timeout=15000) as download_info:
            macro_btn.click()
        return download_info.value
    except Exception as e:
        print(f"No download received from macro slot {slot}: {e}")
        return None


def _trigger_chat_export(page: Page):
    """Click the Export Chat Log button and intercept the download."""
    selectors_to_try = [
        "button[aria-label='Export Chat Log']",
        "button[data-action='export']",
        "a.export-log",
        "a[title='Export Chat Log']",
        "a[data-tooltip='Export Chat Log']",
        "a:has(i.fa-save)",
    ]

    export_btn = None
    for selector in selectors_to_try:
        locator = page.locator(selector).first
        if locator.is_visible():
            export_btn = locator
            print(f"Found export button using selector: {selector}")
            break

    if not export_btn:
        print("Error: Could not find the Export Chat Log button.")
        return None

    with page.expect_download(timeout=10000) as download_info:
        export_btn.click()
    return download_info.value


def download_foundry_exports(url, username, password, output_dir="testdata"):
    """Log in to FoundryVTT once and download both:
      - Campaign data via macro hotbar slot 1
      - Chat log via the Export Chat Log button

    Returns:
        dict with keys 'campaign_data' and 'chat_log' (file paths), or None values on failure.
    """
    result = {"campaign_data": None, "chat_log": None}

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Starting FoundryVTT automation for {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context().new_page()

            if not _login_and_load(page, url, username, password):
                return result

            # --- Campaign data: trigger macro slot 1 ---
            print("Triggering campaign data export macro...")
            download = _trigger_macro_slot(page, slot=1)
            if download:
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                filename = f"campaign-data-{timestamp}.md"
                save_path = os.path.join(output_dir, filename)
                download.save_as(save_path)
                result["campaign_data"] = save_path
                print(f"Campaign data saved to {save_path}")
            else:
                print("Warning: Campaign data macro did not produce a download.")

            # --- Chat log: use export button ---
            print("Accessing chat sidebar...")
            _click_chat_tab(page)

            print("Exporting chat log...")
            download = _trigger_chat_export(page)
            if download:
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                filename = f"foundry-chat-{timestamp}.txt"
                save_path = os.path.join(output_dir, filename)
                download.save_as(save_path)
                result["chat_log"] = save_path
                print(f"Chat log saved to {save_path}")
            else:
                print("Warning: Chat log export did not produce a download.")

            browser.close()

    except Exception as e:
        print(f"Playwright automation failed: {e}")

    return result


def download_foundry_chat_log(url, username, password, output_dir="testdata"):
    """Download only the FoundryVTT chat log. Used by the GUI app.

    Returns:
        str: Path to the downloaded chat log file, or None on failure.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Starting FoundryVTT automation for {url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context().new_page()

            if not _login_and_load(page, url, username, password):
                return None

            _click_chat_tab(page)

            print("Preparing download...")
            download = _trigger_chat_export(page)
            if not download:
                return None

            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"foundry-chat-{timestamp}.txt"
            save_path = os.path.join(output_dir, filename)
            print(f"Saving chat log to {save_path}...")
            download.save_as(save_path)

            browser.close()
            return save_path

    except Exception as e:
        print(f"Playwright automation failed: {e}")
        return None

if __name__ == "__main__":
    # For testing isolation
    from dotenv import load_dotenv
    load_dotenv()
    
    url = os.getenv("FOUNDRY_URL")
    user = os.getenv("FOUNDRY_USERNAME")
    pwd = os.getenv("FOUNDRY_PASSWORD")
    
    if url and user:
        result = download_foundry_chat_log(url, user, pwd)
        print(f"Test Run Result: {result}")
    else:
        print("Please set FOUNDRY_URL and FOUNDRY_USERNAME in .env for testing.")
