"""Test email sending via Logic App"""
import requests
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('LOGIC_APP_EMAIL_URL')
print(f'Logic App URL configured: {url[:80]}...')

# Send test email
payload = {
    'to': 'shantanubhute2@gmail.com',
    'subject': 'Test Email - CIP Digest Subscription Working!',
    'body': '''<html>
<body style="font-family: Arial, sans-serif; padding: 20px;">
<h1 style="color: #1f4e79;">Congratulations!</h1>
<p>Your CIP Digest subscription is now <strong>active</strong>!</p>
<p>You are subscribed to:</p>
<ul>
<li>RACI (Page ID: 17386855)</li>
</ul>
<p>You will receive email notifications whenever this page is updated on Confluence.</p>
<hr>
<p style="color: #666; font-size: 12px;">This is a test email from the CIP Digest system.</p>
</body>
</html>'''
}

print('Sending test email to shantanubhute2@gmail.com...')
response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
print(f'Response status: {response.status_code}')
print(f'Response: {response.text[:200] if response.text else "OK - No body"}')

if response.status_code in [200, 202]:
    print('\n SUCCESS! Email sent. Check your inbox (and spam folder).')
else:
    print('\n FAILED to send email. Check Logic App configuration.')
