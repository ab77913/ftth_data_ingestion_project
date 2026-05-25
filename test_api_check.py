import urllib.request, json

resp = urllib.request.urlopen('http://localhost:8000/api/jobs')
jobs = json.loads(resp.read())
csv_job = [j for j in jobs if '6BA8' in j['source_file']][0]
print('CSV Job ID:', csv_job['id'])

job_id = csv_job['id']
resp2 = urllib.request.urlopen(f'http://localhost:8000/api/records?page=1&page_size=2&job_id={job_id}')
data = json.loads(resp2.read())
print('Cols:', len(data['columns']), '- display_mode:', data['display_mode'])
print('First record secondary_number:', data['records'][0]['raw_data'].get('secondary_number'))
print('First record city:', data['records'][0]['raw_data'].get('city'))
print('First record network_node:', data['records'][0]['raw_data'].get('network_node'))
