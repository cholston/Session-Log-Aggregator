import os
import time
from playwright.sync_api import sync_playwright

def download_foundry_chat_log(url, username, password, output_dir="testdata"):
    """
    Automates the process of logging into FoundryVTT and downloading the chat log.
    
    Args:
        url (str): The FoundryVTT server URL.
        username (str): The username to select from the login dropdown.
        password (str): The password for the user.
        output_dir (str): Directory to save the downloaded log. Defaults to 'testdata'.
        
    Returns:
        str: The path to the downloaded chat log file, or None if failed.
    """
    
    print(f"Starting FoundryVTT automation for {url}")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            # 1. Navigate to URL
            print("Navigating to login page...")
            page.goto(url)
            
            # 2. Login Page Interactivity
            # Wait for user selection dropdown to be visible
            print("Waiting for login form...")
            page.wait_for_selector("select[name='userid']")
            
            # Use javascript to select the option by text content since the value is typically a random ID string
            user_id = page.evaluate(f"""() => {{
                const options = Array.from(document.querySelectorAll("select[name='userid'] option"));
                const userOption = options.find(opt => opt.textContent.trim() === '{username}');
                return userOption ? userOption.value : null;
            }}""")
            
            if not user_id:
                print(f"Error: User '{username}' not found in the login dropdown.")
                return None
                
            page.select_option("select[name='userid']", user_id)
            
            # Enter password if needed
            if password:
                page.fill("input[name='password']", password)
                
            # Click Join button
            print("Joining game...")
            page.click("button[name='join']")
            
            # 3. Wait for game to load
            # Wait for the main UI canvas to exist - this usually means the core game has loaded
            print("Waiting for game canvas to load...")
            
            # The #board or setup element usually indicates the game is loaded
            page.wait_for_selector("#board", timeout=60000) 
            
            # Adding a brief sleep to ensure UI elements settle
            time.sleep(2)
            
            # 4. Interact with the Chat Sidebar
            print("Accessing chat sidebar...")
            # Ensure we are on the chat tab
            chat_tab_selectors = [
                 "button[data-tab='chat']",
                 "a.item[data-tab='chat']",
                 "[data-tab='chat']"
            ]
            
            chat_tab = None
            for selector in chat_tab_selectors:
                locator = page.locator(selector).first
                if locator.is_visible():
                    chat_tab = locator
                    print(f"Found chat tab using selector: {selector}")
                    break
                    
            if chat_tab is not None:
               chat_tab.click()
               time.sleep(1) # Wait for panel to switch
            
            # 5. Export the chat log
            print("Preparing download...")
            
            # Locate the export button. Different Foundry versions use different attributes.
            selectors_to_try = [
                "button[aria-label='Export Chat Log']",
                "button[data-action='export']",
                "a.export-log",
                "a[title='Export Chat Log']",
                "a[data-tooltip='Export Chat Log']",
                "a:has(i.fa-save)"
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
                
            # Intercept download event
            with page.expect_download(timeout=10000) as download_info:
                if export_btn is not None:
                    export_btn.click()
                
            download = download_info.value
            
            # Construct the save path
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"foundry-chat-{timestamp}.txt"
            save_path = os.path.join(output_dir, filename)
            
            print(f"Saving chat log to {save_path}...")
            download.save_as(save_path)
            
            # Close browser gracefully
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
