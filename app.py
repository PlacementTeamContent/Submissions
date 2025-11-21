import streamlit as st
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import os

# =====================================================
# LOAD SECRETS FROM STREAMLIT CLOUD
# =====================================================
DJANGO_USERNAME = st.secrets["DJANGO_USERNAME"]
DJANGO_PASSWORD = st.secrets["DJANGO_PASSWORD"]
BASE_URL = st.secrets["BASE_URL"]

LOGIN_URL = f"{BASE_URL}/admin/login/"
ORG_ASSESSMENT_URL = f"{BASE_URL}/admin/nw_assessments_core/organisationassessment/"
ASSESSMENT_LEVEL_URL = f"{BASE_URL}/admin/nw_assessments_core/assessmentlevel/"
TASK_LIST_URL = f"{BASE_URL}/admin/nw_tasks/task/"

# =====================================================
# SELENIUM CONFIG FOR STREAMLIT CLOUD
# =====================================================

class NxtWaveScraper:
    def __init__(self, username, password):
        self.username = username
        self.password = password

        # Chromium paths used by Streamlit Cloud
        CHROMIUM_PATH = "/usr/bin/chromium"
        CHROMEDRIVER_PATH = "/usr/bin/chromedriver"

        options = webdriver.ChromeOptions()
        options.binary_location = CHROMIUM_PATH
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extenions")
        options.add_argument("--disable-infobars")

        service = Service(CHROMEDRIVER_PATH)
        self.driver = webdriver.Chrome(service=service, options=options)

    # =====================================================
    # LOGIN
    # =====================================================
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

    # =====================================================
    # FIND ASSESSMENT ID
    # =====================================================
    def get_assessment_id_from_org_assessment(self, org_assessment_id):
        search_prefix = org_assessment_id[:8]
        search_url = f"{ORG_ASSESSMENT_URL}?q={search_prefix}"
        st.write(f"➡️ Searching Organisation Assessment with prefix `{search_prefix}`")
        try:
            self.driver.get(search_url)
            wait = WebDriverWait(self.driver, 40)
            assessment_id_cell = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "td.field-assessment_id"))
            )
            assessment_id = assessment_id_cell.text.strip()
            st.write(f"✔️ Found Assessment ID: {assessment_id}")
            return assessment_id
        except TimeoutException:
            st.error("Timeout while retrieving assessment ID. Please check input.")
            return None
        except Exception as e:
            st.error(f"Error fetching assessment ID: {e}")
            return None

    # =====================================================
    # GET TITLE + UNIT IDs
    # =====================================================
    def extract_title_and_unit_id_pairs(self, assessment_id_prefix):
        search_url = f"{ASSESSMENT_LEVEL_URL}?q={assessment_id_prefix}"
        st.write("➡️ Searching Assessment Level for tasks...")
        try:
            self.driver.get(search_url)
            wait = WebDriverWait(self.driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#result_list tbody tr")))
            rows = self.driver.find_elements(By.CSS_SELECTOR, "#result_list tbody tr")

            if not rows:
                st.error("No results found.")
                return []

            tasks_to_process = []
            for row in rows:
                title = row.find_element(By.CSS_SELECTOR, "td.field-title").text.strip()
                unit_id = row.find_element(By.CSS_SELECTOR, "td.field-unit_id").text.strip()
                tasks_to_process.append({"title": title, "unit_id": unit_id})

            st.success(f"Found {len(tasks_to_process)} tasks:")
            st.table(tasks_to_process)
            return tasks_to_process

        except Exception as e:
            st.error(f"Error fetching tasks: {e}")
            return []

    # =====================================================
    # OPEN ADD TASK PAGE
    # =====================================================
    def open_tasks_page_and_click_add(self):
        try:
            st.write("➡️ Opening Add Task form...")
            self.driver.get(f"{TASK_LIST_URL}add/")
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "task_form"))
            )
            st.write("✅ Add Task form loaded.")
            return True
        except Exception as e:
            st.error(f"Error loading Add Task form: {e}")
            return False

    # =====================================================
    # FILL TASK FORM & SUBMIT
    # =====================================================
    def fill_task_form_and_save(self, unit_id, subject):
        try:
            st.write(f"➡️ Filling task form: {subject}...")
            wait = WebDriverWait(self.driver, 20)
            task_type_dropdown = wait.until(
                EC.presence_of_element_located((By.NAME, "task_type"))
            )
            Select(task_type_dropdown).select_by_value(subject)

            input_data = wait.until(EC.element_to_be_clickable((By.NAME, "input_data")))
            input_data.clear()
            input_data.send_keys(f'{{"exam_id": "{unit_id}"}}')

            save_button = wait.until(EC.element_to_be_clickable((By.NAME, "_save")))
            save_button.click()

            st.success("Task submitted. Monitoring status...")
            return True

        except Exception as e:
            st.error(f"Error saving task: {e}")
            return False

    # =====================================================
    # MONITOR TASK STATUS
    # =====================================================
    def poll_and_extract_output(self, title, subject):
        st.write(f"➡️ Checking status for '{title}'...")
        try:
            wait = WebDriverWait(self.driver, 20)
            self.driver.get(TASK_LIST_URL)

            for i in range(30):
                self.driver.refresh()
                time.sleep(2)

                status_element = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.field-task_status"))
                )
                status_text = status_element.text.strip().upper()
                st.write(f"Status attempt {i+1}: {status_text}")

                if "SUCCESS" in status_text:
                    st.success("Task completed!")
                    return self.extract_task_output(wait, title, subject)

                if "FAIL" in status_text:
                    st.error("Task failed.")
                    return False

                time.sleep(5)

            st.error("Task timed out.")
            return False

        except Exception as e:
            st.error(f"Error monitoring task: {e}")
            return False

    # =====================================================
    # GET TASK OUTPUT
    # =====================================================
    def extract_task_output(self, wait, title, subject):
        st.write(f"➡️ Extracting output for '{title}'...")

        try:
            task_output = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.field-task_output"))
            ).text.strip()

            json_text = task_output.split(":", 1)[1].strip() if ":" in task_output else task_output
            st.code(json_text, language="json")

            data = json.loads(json_text)

            key_map = {
                "GET_CODING_EXAM_SUBMISSION_STATS": "coding_exam_submission_stats_url",
                "GET_MCQ_EXAM_SUBMISSION_STATS": "mcq_exam_submission_stats_url",
                "GET_SQL_CODING_EXAM_SUBMISSION_STATS": "sql_coding_exam_submission_stats_url",
                "GET_HTML_CODING_EXAM_SUBMISSION_STATS": "html_coding_exam_submission_stats_url",
                "GET_HTML_CODING_EXAM_LATEST_SUBMISSION_STATS": "html_coding_exam_latest_submission_stats_url",
            }

            url_key = key_map.get(subject)
            download_url = data.get("response", {}).get(url_key)

            if download_url:
                st.markdown(f"### ⬇️ Download CSV for {title}")
                st.markdown(f"[Click here to download]({download_url})")
                return True

            st.warning("Could not find expected URL in task output.")
            return False

        except Exception as e:
            st.error(f"Error extracting output: {e}")
            return False

    def close_browser(self):
        try:
            self.driver.quit()
        except:
            pass


# =====================================================
# STREAMLIT UI (UNCHANGED EXCEPT DRIVER FIXES)
# =====================================================

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

TITLE_TO_SUBJECT_MAP = {
    "CODING": "GET_CODING_EXAM_SUBMISSION_STATS",
    "SQL": "GET_SQL_CODING_EXAM_SUBMISSION_STATS",
    "HTML": "GET_HTML_CODING_EXAM_SUBMISSION_STATS",
    "MCQ": "GET_MCQ_EXAM_SUBMISSION_STATS",
    "APTITUDE": "GET_MCQ_EXAM_SUBMISSION_STATS",
    "ENGLISH": "GET_MCQ_EXAM_SUBMISSION_STATS",
}

def auto_assign_subject(title):
    t = title.upper()
    for keyword, subject in TITLE_TO_SUBJECT_MAP.items():
        if keyword in t:
            return subject
    return subject_options[0]

# =====================================================
# INITIAL UI PAGE
# =====================================================
if st.session_state.stage == "initial":
    with st.container(border=True):
        st.header("Step 1: Find Assessable Tasks")
        org_assessment_id_input = st.text_input("Organisation Assessment ID")

        if st.button("Find Tasks", type="primary"):
            if not org_assessment_id_input:
                st.warning("Please enter an Organisation Assessment ID.")
            else:
                scraper = NxtWaveScraper(DJANGO_USERNAME, DJANGO_PASSWORD)
                st.session_state.scraper = scraper

                if scraper.login():
                    assessment_id = scraper.get_assessment_id_from_org_assessment(org_assessment_id_input)
                    if assessment_id:
                        tasks = scraper.extract_title_and_unit_id_pairs(assessment_id[:8])
                        if tasks:
                            st.session_state.tasks_found = tasks
                            st.session_state.stage = "selection"
                            st.rerun()
                scraper.close_browser()

# =====================================================
# TASK SELECTION PAGE
# =====================================================
if st.session_state.stage == "selection":
    with st.container(border=True):
        st.header("Step 2: Confirm Tasks & Subjects")

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
                    default_subject = auto_assign_subject(task["title"])
                    index = subject_options.index(default_subject)
                    subject = st.selectbox("Select Subject", subject_options, index=index, key=f"subject_{i}")

                if selected:
                    tasks_to_run.append({
                        "title": task["title"],
                        "unit_id": task["unit_id"],
                        "subject": subject
                    })

            submit_btn = st.form_submit_button("Process Selected Tasks", type="primary")

    if submit_btn:
        scraper = st.session_state.scraper
        if scraper is None:
            scraper = NxtWaveScraper(DJANGO_USERNAME, DJANGO_PASSWORD)
            scraper.login()

        for task in tasks_to_run:
            title = task["title"]
            subject = task["subject"]
            unit_id = task["unit_id"]

            st.subheader(f"Processing: {title}")
            st.write(f"Subject: {subject}")

            if scraper.open_tasks_page_and_click_add():
                if scraper.fill_task_form_and_save(unit_id, subject):
                    scraper.poll_and_extract_output(title, subject)

        scraper.close_browser()
        st.success("All tasks processed!")
        st.balloons()

        st.session_state.stage = "initial"
        st.session_state.tasks_found = []
        st.session_state.scraper = None
        st.rerun()
