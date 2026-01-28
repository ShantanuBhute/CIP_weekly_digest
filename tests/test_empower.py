"""Test EMPower email for Naruto"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_digest_generator import generate_page_summary_email
import json

result = generate_page_summary_email('439124075', 'EMPower AI Research', 6, True, 'Added Naruto section')
with open(result['json_file']) as f:
    data = json.load(f)
    if 'naruto' in data['summary'].lower():
        print('NARUTO FOUND')
        idx = data['summary'].lower().find('naruto')
        print(data['summary'][max(0,idx-30):idx+250])
    else:
        print('NARUTO NOT FOUND')
        print(data['summary'])
