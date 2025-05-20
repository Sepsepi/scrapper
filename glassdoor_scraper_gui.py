import tkinter as tk
from tkinter import ttk, messagebox
from playwright.sync_api import sync_playwright
import threading
import time
import webbrowser

class GlassdoorScraperApp:
    def __init__(self, root):
        self.root = root
        root.title("Glassdoor Job Scraper")
        root.geometry("800x600")

        # Style
        self.style = ttk.Style()
        self.style.theme_use("clam") # Using a theme that supports more styling options

        # --- Input Frame ---
        input_frame = ttk.LabelFrame(root, text="Search Criteria", padding="10")
        input_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(input_frame, text="Keyword:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.keyword_var = tk.StringVar(value="Java")
        self.keyword_entry = ttk.Entry(input_frame, textvariable=self.keyword_var, width=40)
        self.keyword_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="Country:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.country_var = tk.StringVar(value="Norway")
        self.country_entry = ttk.Entry(input_frame, textvariable=self.country_var, width=40)
        self.country_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        input_frame.columnconfigure(1, weight=1) # Make entry widgets expand

        self.scrape_button = ttk.Button(input_frame, text="Scrape Jobs", command=self.start_scraping_thread)
        self.scrape_button.grid(row=2, column=0, columnspan=2, pady=10)

        # --- Results Frame ---
        results_frame = ttk.LabelFrame(root, text="Results", padding="10")
        results_frame.pack(padx=10, pady=10, fill="both", expand=True)

        self.results_tree = ttk.Treeview(results_frame, columns=("Company", "Job Title", "Link"), show="headings")
        self.results_tree.heading("Company", text="Company Name")
        self.results_tree.heading("Job Title", text="Job Title")
        self.results_tree.heading("Link", text="Direct Link")

        self.results_tree.column("Company", width=200, anchor="w")
        self.results_tree.column("Job Title", width=300, anchor="w")
        self.results_tree.column("Link", width=250, anchor="w")

        # Add scrollbars
        vsb = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        hsb = ttk.Scrollbar(results_frame, orient="horizontal", command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.results_tree.pack(fill="both", expand=True)

        self.results_tree.bind("<Double-1>", self.open_link)

        # --- Status Bar ---
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w", padding="2 5")
        status_bar.pack(side=tk.BOTTOM, fill="x")

    def open_link(self, event):
        try:
            item_id = self.results_tree.selection()[0]
            item = self.results_tree.item(item_id)
            link = item['values'][2] # Link is the 3rd column
            if link and link != "N/A" and link.startswith("http"):
                webbrowser.open_new_tab(link)
                self.status_var.set(f"Opened: {link}")
            elif link:
                self.status_var.set(f"Cannot open invalid link: {link}")
        except IndexError:
            self.status_var.set("No item selected or link available.")
        except Exception as e:
            self.status_var.set(f"Error opening link: {e}")
            messagebox.showerror("Error", f"Could not open link: {e}")


    def start_scraping_thread(self):
        self.scrape_button.config(state=tk.DISABLED)
        self.status_var.set("Scraping started... Please wait.")
        # Clear previous results
        for i in self.results_tree.get_children():
            self.results_tree.delete(i)

        keyword = self.keyword_var.get()
        country = self.country_var.get()

        if not keyword or not country:
            messagebox.showerror("Input Error", "Keyword and Country cannot be empty.")
            self.scrape_button.config(state=tk.NORMAL)
            self.status_var.set("Ready")
            return

        # Run scraping in a separate thread to avoid freezing the GUI
        thread = threading.Thread(target=self.scrape_and_update_gui, args=(keyword, country))
        thread.daemon = True # Allows main program to exit even if threads are running
        thread.start()

    def update_gui_with_results(self, job_listings):
        if not job_listings:
            self.status_var.set("No jobs found or an error occurred.")
            messagebox.showinfo("Scraping Complete", "No job listings found for the given criteria.")
            return

        if isinstance(job_listings, dict) and "error" in job_listings: # Handle error passed as dict
             messagebox.showerror("Scraping Error", job_listings["error"])
             self.status_var.set(f"Error: {job_listings['error']}")
             return
        
        if isinstance(job_listings, list) and len(job_listings) > 0 and "error" in job_listings[0]:
            messagebox.showerror("Scraping Error", job_listings[0]["error"])
            self.status_var.set(f"Error: {job_listings[0]['error']}")
            return

        for job in job_listings:
            self.results_tree.insert("", tk.END, values=(job.get("company_name", "N/A"), 
                                                        job.get("job_title", "N/A"), 
                                                        job.get("job_link", "N/A")))
        self.status_var.set(f"Scraping complete. Found {len(job_listings)} listings.")
        messagebox.showinfo("Scraping Complete", f"Found {len(job_listings)} job listings.")


    def scrape_and_update_gui(self, keyword, country):
        try:
            job_listings = self._scrape_glassdoor_internal(keyword, country)
            # Schedule GUI update on the main thread
            self.root.after(0, self.update_gui_with_results, job_listings)
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            print(error_message) # Log to console as well
            self.root.after(0, self.update_gui_with_results, [{"error": error_message}]) # Pass error to GUI
        finally:
            # Re-enable button on the main thread
            self.root.after(0, lambda: self.scrape_button.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.status_var.set("Ready" if not self.results_tree.get_children() else self.status_var.get()))


    def _scrape_glassdoor_internal(self, keyword, country):
        job_listings = []
        with sync_playwright() as p:
            # browser = p.chromium.launch(headless=True) # Set to True for less intrusive scraping
            browser = p.chromium.launch(headless=False) # False for debugging
            page = browser.new_page()
            
            self.root.after(0, lambda: self.status_var.set("Navigating to Glassdoor..."))
            try:
                page.goto("https://www.glassdoor.com/Job/index.htm", timeout=60000)
                print("Navigated to Glassdoor jobs index.")
                self.root.after(0, lambda: self.status_var.set("Handling cookie banners..."))
                time.sleep(3) # Give time for modals or cookie banners

                cookie_selectors = [
                    "button#onetrust-accept-btn-handler",
                    "//button[contains(text(), 'Accept Cookies') or contains(text(), 'Allow All') or contains(text(), 'Accept all')]",
                    "button[aria-label*='Accept']"
                ]
                for sel in cookie_selectors:
                    if page.query_selector(sel):
                        try:
                            page.click(sel, timeout=5000)
                            print(f"Clicked cookie banner with selector: {sel}")
                            time.sleep(2)
                            break # Assume one banner is enough
                        except Exception as e:
                            print(f"Could not click cookie banner {sel}: {e}")
                
                self.root.after(0, lambda: self.status_var.set("Filling search criteria..."))
                # Fill keyword
                keyword_input_selectors = [
                    'input[data-test="search-job-keyword-input-internal"]', 'input#searchJobKeyword',
                    'input[placeholder*="Job title, keywords, or company"]', 'input[aria-label*="Search Keyword"]',
                    'input[name="keyword"]', # Added
                    '//input[@placeholder="Job title, keywords, or company"]', # Added XPath
                    '//input[contains(@aria-label, "Search Keyword")]', # Added XPath
                    'input[type="text"][role="combobox"]' # Added generic
                ]
                filled_keyword = False
                for sel in keyword_input_selectors:
                    if page.query_selector(sel):
                        page.fill(sel, keyword)
                        print(f"Filled keyword '{keyword}' into selector: {sel}")
                        filled_keyword = True
                        break
                if not filled_keyword: return [{"error": "Could not find keyword input."}]

                # Fill location
                location_input_selectors = [
                    'input[data-test="search-job-location-input-internal"]', 'input#searchJobLocation',
                    'input[placeholder*="Location"]', 'input[aria-label*="Search Location"]'
                ]
                filled_location = False
                for sel in location_input_selectors:
                    if page.query_selector(sel):
                        page.fill(sel, "") # Clear field
                        time.sleep(0.5)
                        page.fill(sel, country)
                        print(f"Filled location '{country}' into selector: {sel}")
                        filled_location = True
                        # Sometimes a dropdown appears, try to click the first suggestion or press Enter
                        time.sleep(1) # Wait for suggestions
                        # Common suggestion selector: div[data-test*='suggestion'] or ul[role='listbox'] li
                        suggestion_selector = "div[data-test*='suggestion']:visible, ul[role='listbox'] li:visible"
                        if page.query_selector(suggestion_selector):
                            try:
                                page.click(suggestion_selector, timeout=3000)
                                print("Clicked location suggestion.")
                            except:
                                print("Could not click suggestion, trying Enter.")
                                page.press(sel, "Enter") # Press Enter in the input field
                        else:
                             page.press(sel, "Enter") # Press Enter if no obvious suggestion box
                        break
                if not filled_location: return [{"error": "Could not find location input."}]
                
                self.root.after(0, lambda: self.status_var.set("Submitting search..."))
                # Click search button (or rely on Enter press from location)
                search_button_selectors = [
                    'button[data-test="search-button"]', 'button#searchJobButton',
                    'button[type="submit"]', '//button[span[contains(text(),"Search")]]'
                ]
                clicked_search = False
                # Check if Enter already navigated
                if "Search" not in page.url: # A basic check, might need refinement
                    for sel in search_button_selectors:
                        if page.query_selector(sel) and page.query_selector(sel).is_visible() and page.query_selector(sel).is_enabled():
                            try:
                                page.click(sel, timeout=10000)
                                print(f"Clicked search button with selector: {sel}")
                                clicked_search = True
                                break
                            except Exception as e:
                                print(f"Failed to click search button {sel}: {e}")
                    if not clicked_search:
                        print("Search button not clicked, relying on previous Enter or page already loaded.")
                else:
                    print("URL indicates search might have already happened.")

                page.wait_for_load_state("networkidle", timeout=45000)
                print("Search results page loaded/stabilized.")
                self.root.after(0, lambda: self.status_var.set("Search results loaded. Scraping jobs..."))
                time.sleep(3) # Allow dynamic content

                # Handle potential pop-ups (sign-in, alerts etc.)
                modal_close_selectors = [
                    "button.modal_closeIcon", "button[aria-label='Close']", "span.SVGInline.modal_closeIcon",
                    "button[data-test='modal-close']", "div[aria-label='dialog'] button[aria-label*='Close']"
                ]
                for sel in modal_close_selectors:
                    if page.query_selector(sel) and page.query_selector(sel).is_visible():
                        try:
                            page.click(sel, timeout=3000, force=True) # force click if needed
                            print(f"Closed a modal with selector: {sel}")
                            time.sleep(1)
                        except Exception as e:
                            print(f"Could not click modal close {sel}: {e}")

                # Scraping loop for multiple pages
                for page_num in range(1, 4): # Scrape up to 3 pages
                    self.root.after(0, lambda current_page=page_num: self.status_var.set(f"Scraping page {current_page}..."))
                    
                    job_card_selector = "li.react-job-listing, li[data-test='job-listing'], article[data-test='job-listing']"
                    try:
                        page.wait_for_selector(job_card_selector, timeout=20000)
                    except Exception as e:
                        print(f"Job cards not found on page {page_num}. Error: {e}")
                        if page_num == 1: # If no jobs on first page, likely no results
                            return [{"error": f"No job listings found or page structure changed. ({e})"}]
                        break 

                    job_elements = page.query_selector_all(job_card_selector)
                    if not job_elements:
                        print(f"No job elements found on page {page_num}.")
                        if page_num == 1: return [{"error": "No job listings found."}]
                        break
                    
                    print(f"Found {len(job_elements)} job elements on page {page_num}.")

                    for job_element in job_elements:
                        company_name, job_title_text, job_link = "N/A", "N/A", "N/A"
                        
                        company_selectors = [
                            "div[data-test='employer-name']", "div[class*='EmployerProfile_employerName']",
                            "a[data-test='ei-employer-name']", "div[class*='job-search-key'] span"
                        ]
                        for sel in company_selectors:
                            el = job_element.query_selector(sel)
                            if el: company_name = el.inner_text().strip(); break
                        
                        title_link_selectors = [
                            "a[data-test='job-title']", "a[data-test='job-link']",
                            "div[class*='JobCard_jobTitle'] a", "a[class*='jobLink']",
                            "a[href*='/partner/jobListing.htm']"
                        ]
                        for sel in title_link_selectors:
                            el = job_element.query_selector(sel)
                            if el:
                                job_title_text = el.inner_text().strip()
                                raw_link = el.get_attribute("href")
                                if raw_link:
                                    job_link = "https://www.glassdoor.com" + raw_link if raw_link.startswith("/") else raw_link
                                break
                        
                        if job_title_text == "N/A": # Fallback for title if not in link
                            title_selectors = ["div[data-test='job-title']", "div[class*='JobCard_jobTitle']"]
                            for sel in title_selectors:
                                el = job_element.query_selector(sel)
                                if el: job_title_text = el.inner_text().strip(); break

                        if company_name != "N/A" or job_title_text != "N/A":
                            job_listings.append({
                                "company_name": company_name, "job_title": job_title_text, "job_link": job_link
                            })
                    
                    # Pagination
                    next_button_selectors = [
                        "button[data-test='pagination-next']", "li.next a", 
                        "button[aria-label='Next']", "//button[span[contains(text(),'Next')]]",
                        "a[data-test='pagination-next']"
                    ]
                    next_button_found = False
                    for sel in next_button_selectors:
                        next_button = page.query_selector(sel)
                        if next_button and next_button.is_enabled() and next_button.is_visible():
                            try:
                                next_button.click(timeout=10000)
                                page.wait_for_load_state("networkidle", timeout=20000)
                                time.sleep(3) # Wait for new content
                                print(f"Clicked 'Next' button (selector: {sel}), moved to page {page_num + 1}")
                                next_button_found = True
                                break 
                            except Exception as e:
                                print(f"Could not click 'Next' button ({sel}): {e}")
                    
                    if not next_button_found:
                        print("No 'Next' button found or enabled. Ending pagination.")
                        break
                
            except Exception as e:
                print(f"Error during scraping: {e}")
                browser.close()
                return [{"error": f"Scraping failed: {e}"}] # Return error as a list with a dict
            
            browser.close()
            return job_listings

if __name__ == "__main__":
    root = tk.Tk()
    app = GlassdoorScraperApp(root)
    root.mainloop()
