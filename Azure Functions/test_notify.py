"""Test email notification"""
from dotenv import load_dotenv
load_dotenv()

from email_sender import notify_subscribers_for_page

# Test sending to subscribers for RACI page (17386855)
print('Testing notify_subscribers_for_page...')
result = notify_subscribers_for_page(
    page_id='17386855',
    email_subject='Update: RACI (v16) - Test',
    email_body='<h1>RACI Page Updated</h1><p>This is a test notification that the RACI page has been updated.</p><p>Version: 16</p>'
)
print(f'Result: {result}')
