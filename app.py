import streamlit as st
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuration ---
DJANGO_USERNAME = "ravikiran.perla"
DJANGO_PASSWORD = "273hFat@"
BASE_URL = "https://nxtwave-assessments-backend-topin-prod-apis.ccbp.in"
LOGIN_URL = f"{BASE_URL}/admin/login/"
ORG_ASSESSMENT_URL = f"{BASE_URL}/admin/nw_assessments_core/organisationassessment/"
ASSESSMENT_LEVEL_URL = f"{BASE_URL}/admin/nw_assessments_core/assessmentlevel/"
TASK_LIST_URL = f"{BASE_URL}/admin/nw_tasks/task/"

class NxtWaveScraper:
    # --- The core automation class remains the same as it is working correctly ---
    def __init__(self, username, password):
        self.username = username
        self.password = password
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        # options.add_argument('--headless')
        self.driver = webdriver.Chrome(service=service, options=options)

    def login(self):
        st.write("➡️ Navigating to login page...")
        self.driver.get(LOGIN_URL)
        try:
            wait = WebDriverWait(self.driver, 10)
            username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
            username_field.send_keys(self.username)
            self.driver.find_element(By.NAME, "password").send_keys(self.password)
            self.driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
            wait.until(EC.presence_of_element_located((By.ID, "content")))
            st.write("✅ Login Successful!")
            return True
        except Exception as e:
            st.error(f"Login error: {e}")
            return False

    def get_assessment_id_from_org_assessment(self, org_assessment_id):
        search_prefix = org_assessment_id[:8]
        search_url = f"{ORG_ASSESSMENT_URL}?q={search_prefix}"
        st.write(f"➡️ Searching Organisation Assessment with prefix `{search_prefix}`")
        try:
            self.driver.get(search_url)
            wait = WebDriverWait(self.driver, 40)
            assessment_id_cell = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "td.field-assessment_id")))
            assessment_id = assessment_id_cell.text.strip()
            st.write(f"✔️ Found Assessment ID: {assessment_id}")
            return assessment_id
        except TimeoutException:
            st.error("Timeout while retrieving assessment ID. Please check input.")
            return None
        except Exception as e:
            st.error(f"Error fetching assessment ID: {e}")
            return None

    def extract_title_and_unit_id_pairs(self, assessment_id_prefix):
        search_url = f"{ASSESSMENT_LEVEL_URL}?q={assessment_id_prefix}"
        st.write(f"➡️ Searching Assessment Level for Title/Unit ID pairs...")
        try:
            self.driver.get(search_url)
            wait = WebDriverWait(self.driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#result_list tbody tr")))
            rows = self.driver.find_elements(By.CSS_SELECTOR, "#result_list tbody tr")
            if not rows:
                st.error("Error: No result rows found on the page.")
                return []
            tasks_to_process = []
            for row in rows:
                title = row.find_element(By.CSS_SELECTOR, "td.field-title").text.strip()
                unit_id = row.find_element(By.CSS_SELECTOR, "td.field-unit_id").text.strip()
                tasks_to_process.append({"title": title, "unit_id": unit_id})
            st.success(f"✔️ Found {len(tasks_to_process)} assessable tasks:")
            st.table(tasks_to_process)
            return tasks_to_process
        except Exception as e:
            st.error(f"Error fetching Title/Unit ID pairs: {e}")
            return []

    def open_tasks_page_and_click_add(self):
        try:
            st.write("➡️ Opening Add Task form directly...")
            self.driver.get(f"{TASK_LIST_URL}add/")
            wait = WebDriverWait(self.driver, 20)
            wait.until(EC.presence_of_element_located((By.ID, "task_form")))
            st.write("✅ Add Task form loaded.")
            return True
        except Exception as e:
            st.error(f"Error loading Add Task form: {e}")
            return False

    def fill_task_form_and_save(self, unit_id, subject):
        try:
            st.write(f"➡️ Filling task form with subject '{subject}'...")
            wait = WebDriverWait(self.driver, 20)
            task_type_dropdown = wait.until(EC.presence_of_element_located((By.NAME, "task_type")))
            Select(task_type_dropdown).select_by_value(subject)
            input_data = wait.until(EC.element_to_be_clickable((By.NAME, "input_data")))
            input_data.clear()
            input_data.send_keys(f'{{"exam_id": "{unit_id}"}}')
            save_button = wait.until(EC.element_to_be_clickable((By.NAME, "_save")))
            st.write("✅ Submitting form...")
            save_button.click()
            st.success("Task form submitted. Now preparing to monitor the task.")
            return True
        except Exception as e:
            st.error(f"Error filling task form: {e}")
            return False

    def poll_and_extract_output(self, title, subject):
        st.write(f"➡️ Monitoring task for '{title}'...")
        try:
            wait = WebDriverWait(self.driver, 20)
            self.driver.get(TASK_LIST_URL)
            self.driver.refresh()
            time.sleep(2)
            first_task_link = wait.until(EC.element_to_be_clickable((By.XPATH, "//table[@id='result_list']/tbody/tr[1]/th/a")))
            first_task_link.click()
            for i in range(30):
                status_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.field-task_status")))
                status_text = status_element.text.strip().upper()
                st.write(f"  - Attempt {i+1}: Task status for '{title}' is '{status_text}'")
                if "SUCCESS" in status_text:
                    st.success(f"✅ Task status for '{title}' is SUCCESS!")
                    return self.extract_task_output(wait, title, subject)
                elif "FAILURE" in status_text or "FAILED" in status_text:
                    st.error(f"❌ Task status for '{title}' is {status_text}. Halting.")
                    return False
                st.info("  - Task in progress, refreshing in 10 seconds...")
                time.sleep(10)
                self.driver.refresh()
            st.error(f"Polling timed out for '{title}'.")
            return False
        except Exception as e:
            st.error(f"An error occurred while monitoring task for '{title}': {e}")
            return False

    def extract_task_output(self, wait, title, subject):
        st.write(f"➡️ Extracting output for '{title}'...")
        try:
            task_output_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.field-task_output")))
            full_text = task_output_container.text.strip()
            json_text = full_text.split(':', 1)[1].strip() if ':' in full_text else full_text
            if not json_text:
                st.error("❌ Found the output element, but it was empty.")
                return False
            st.subheader(f"Raw Task Output for {title}")
            st.code(json_text, language="json")
            data = json.loads(json_text)
            key_map = {
                "GET_CODING_EXAM_SUBMISSION_STATS": "coding_exam_submission_stats_url",
                "GET_MCQ_EXAM_SUBMISSION_STATS": "mcq_exam_submission_stats_url",
                "GET_SQL_CODING_EXAM_SUBMISSION_STATS": "sql_coding_exam_submission_stats_url",
                "GET_HTML_CODING_EXAM_SUBMISSION_STATS": "html_coding_exam_submission_stats_url",
                "GET_HTML_CODING_EXAM_LATEST_SUBMISSION_STATS": "html_coding_exam_latest_submission_stats_url"
            }
            url_key = key_map.get(subject)
            download_url = data.get("response", {}).get(url_key)
            if download_url:
                st.subheader(f"⬇️ Download Link for {title}")
                st.markdown(f"**[Click Here to Download CSV for {title}]({download_url})**")
                return True
            else:
                st.warning(f"⚠️ Could not find the expected download URL with key '{url_key}' in the Task Output.")
                return False
        except Exception as e:
            st.error(f"❌ An unexpected error occurred while extracting the output for '{title}': {e}")
            return False

    def close_browser(self):
        self.driver.quit()

# --- Streamlit UI and Helper Functions ---
st.set_page_config(page_title="Submission Downloader", layout="wide")
st.title("🚀 NxtWave Submission Downloader")

if 'stage' not in st.session_state:
    st.session_state.stage = "initial"
if 'tasks_found' not in st.session_state:
    st.session_state.tasks_found = []
if 'scraper' not in st.session_state:
    st.session_state.scraper = None

subject_options = [
    "GET_CODING_EXAM_SUBMISSION_STATS",
    "GET_MCQ_EXAM_SUBMISSION_STATS",
    "GET_SQL_CODING_EXAM_SUBMISSION_STATS",
    "GET_HTML_CODING_EXAM_SUBMISSION_STATS",
    "GET_HTML_CODING_EXAM_LATEST_SUBMISSION_STATS",
]

# <<< --- NEW: The "Brain" for Auto-Assignment --- >>>
# This dictionary maps keywords (in uppercase) to the subject values.
# You can easily add more keywords here.
TITLE_TO_SUBJECT_MAP = {
    "CODING": "GET_CODING_EXAM_SUBMISSION_STATS",
    "SQL": "GET_SQL_CODING_EXAM_SUBMISSION_STATS",
    "HTML": "GET_HTML_CODING_EXAM_SUBMISSION_STATS",
    "MCQ": "GET_MCQ_EXAM_SUBMISSION_STATS",
    "APTITUDE": "GET_MCQ_EXAM_SUBMISSION_STATS", # Assuming Aptitude is MCQ
    "ENGLISH": "GET_MCQ_EXAM_SUBMISSION_STATS",   # Assuming English is MCQ
}

def auto_assign_subject(title):
    """Takes a title and returns a suggested subject based on keywords."""
    title_upper = title.upper()
    for keyword, subject in TITLE_TO_SUBJECT_MAP.items():
        if keyword in title_upper:
            return subject
    return subject_options[0] # Default to the first option if no match

# --- UI Stage 1: Initial Input ---
if st.session_state.stage == "initial":
    with st.container(border=True):
        st.header("Step 1: Find Assessable Tasks")
        org_assessment_id_input = st.text_input("Organisation Assessment ID")
        if st.button("Find Tasks", type="primary"):
            if not org_assessment_id_input:
                st.warning("Please enter an Organisation Assessment ID.")
            else:
                st.header("Discovery Log")
                with st.spinner("Finding tasks... This will take a moment."):
                    scraper = NxtWaveScraper(DJANGO_USERNAME, DJANGO_PASSWORD)
                    st.session_state.scraper = scraper
                    if scraper.login():
                        assessment_id = scraper.get_assessment_id_from_org_assessment(org_assessment_id_input)
                        if assessment_id:
                            assessment_id_prefix = assessment_id[:8]
                            tasks = scraper.extract_title_and_unit_id_pairs(assessment_id_prefix)
                            if tasks:
                                st.session_state.tasks_found = tasks
                                st.session_state.stage = "selection"
                                st.rerun()
                if st.session_state.stage != "selection":
                    if st.session_state.scraper:
                        st.session_state.scraper.close_browser()
                        st.session_state.scraper = None

# --- UI Stage 2: Task Selection (with Auto-Assignment) and Execution ---
if st.session_state.stage == "selection":
    with st.container(border=True):
        st.header("Step 2: Confirm Tasks and Subjects")
        st.info("The tool has automatically assigned subjects based on the task titles. You can override them if needed.")
        
        with st.form("task_selection_form"):
            tasks_to_run = []
            for i, task in enumerate(st.session_state.tasks_found):
                st.markdown("---")
                cols = st.columns([1, 4, 4])
                with cols[0]:
                    selected = st.checkbox("Process?", key=f"select_{i}", value=True)
                with cols[1]:
                    st.markdown(f"**Title:** `{task['title']}`")
                    st.caption(f"Unit ID: {task['unit_id']}")
                with cols[2]:
                    # <<< --- NEW: Auto-assignment logic --- >>>
                    default_subject = auto_assign_subject(task['title'])
                    default_index = subject_options.index(default_subject) if default_subject in subject_options else 0
                    
                    subject = st.selectbox("Assign Subject", subject_options, key=f"subject_{i}", index=default_index)
                
                if selected:
                    tasks_to_run.append({"title": task['title'], "unit_id": task['unit_id'], "subject": subject})

            process_button = st.form_submit_button("Process Selected Tasks", type="primary")

    if process_button:
        st.header("Execution Log")
        log_container = st.container(border=True)
        with log_container:
            if not tasks_to_run:
                st.warning("No tasks were selected to process."); st.stop()

            scraper = st.session_state.scraper
            total_tasks = len(tasks_to_run)
            all_tasks_successful = True
            for i, task_data in enumerate(tasks_to_run):
                title = task_data["title"]; unit_id = task_data["unit_id"]; subject = task_data["subject"]
                st.subheader(f"--- Processing Task {i+1} of {total_tasks} for Title: '{title}' ---")
                st.info(f"Using Subject: '{subject}' for Unit ID: {unit_id}")
                
                if not scraper.open_tasks_page_and_click_add():
                    all_tasks_successful = False; break
                if not scraper.fill_task_form_and_save(unit_id, subject):
                    all_tasks_successful = False; break
                if not scraper.poll_and_extract_output(title, subject):
                    all_tasks_successful = False; break
                
                st.success(f"Task for '{title}' completed successfully.")
            
            if all_tasks_successful:
                st.header("✅ All selected tasks have been processed successfully.")
                st.balloons()
        
        if scraper: scraper.close_browser()
        st.session_state.stage = "initial"
        st.session_state.tasks_found = []
        st.session_state.scraper = None
        if st.button("Start New Process"):
            st.rerun()