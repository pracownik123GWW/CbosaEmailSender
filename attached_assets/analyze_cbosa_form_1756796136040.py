#!/usr/bin/env python3
"""
Analyze CBOSA form to understand date field requirements
"""

import requests
from bs4 import BeautifulSoup
import json

def analyze_cbosa_form():
    """Fetch and analyze the CBOSA search form"""
    url = "https://orzeczenia.nsa.gov.pl/cbo/query"
    
    print("🔍 Analyzing CBOSA Search Form")
    print("=" * 60)
    
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find the main form
    form = soup.find('form', {'action': '/cbo/search'})
    if not form:
        form = soup.find('form')
    
    print(f"✅ Found form with action: {form.get('action', 'N/A')}")
    print(f"   Method: {form.get('method', 'N/A')}")
    
    # Find all date-related input fields
    print("\n📅 Date-related fields:")
    date_inputs = form.find_all(['input', 'select'], attrs={'name': lambda x: x and ('dat' in x.lower() or 'date' in x.lower())})
    
    for inp in date_inputs:
        field_type = inp.name
        name = inp.get('name', '')
        input_type = inp.get('type', 'text')
        value = inp.get('value', '')
        placeholder = inp.get('placeholder', '')
        
        print(f"\n  Field: {name}")
        print(f"    Type: {field_type} ({input_type})")
        print(f"    Value: {value}")
        print(f"    Placeholder: {placeholder}")
        
        # Check for any data attributes
        for attr, val in inp.attrs.items():
            if attr.startswith('data-'):
                print(f"    {attr}: {val}")
    
    # Look for date-related labels
    print("\n🏷️  Date-related labels:")
    labels = form.find_all('label')
    for label in labels:
        text = label.get_text(strip=True)
        if 'dat' in text.lower() or 'termin' in text.lower():
            print(f"  - {text}")
            associated_input = None
            if label.get('for'):
                associated_input = form.find(id=label.get('for'))
            if not associated_input and label.find_next_sibling(['input', 'select']):
                associated_input = label.find_next_sibling(['input', 'select'])
            
            if associated_input:
                print(f"    Associated field: {associated_input.get('name', 'N/A')}")
    
    # Extract all form fields for complete picture
    print("\n📋 All form fields:")
    all_inputs = form.find_all(['input', 'select', 'textarea'])
    fields_dict = {}
    
    for inp in all_inputs:
        name = inp.get('name', '')
        if name:
            field_info = {
                'type': inp.name,
                'input_type': inp.get('type', 'text'),
                'value': inp.get('value', ''),
                'placeholder': inp.get('placeholder', ''),
                'class': inp.get('class', []),
                'id': inp.get('id', '')
            }
            
            # For select elements, get options
            if inp.name == 'select':
                options = []
                for opt in inp.find_all('option'):
                    options.append({
                        'value': opt.get('value', ''),
                        'text': opt.get_text(strip=True)
                    })
                field_info['options'] = options
            
            fields_dict[name] = field_info
    
    # Save to JSON for analysis
    with open('cbosa_form_fields.json', 'w', encoding='utf-8') as f:
        json.dump(fields_dict, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved {len(fields_dict)} fields to cbosa_form_fields.json")
    
    # Look specifically for date fields
    for name, info in fields_dict.items():
        if 'dat' in name.lower() or 'date' in name.lower():
            print(f"\n  🗓️  {name}: {info}")

if __name__ == "__main__":
    analyze_cbosa_form()