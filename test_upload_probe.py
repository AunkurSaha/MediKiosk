import urllib.request
import json
import time

login_req = urllib.request.Request(
    'http://127.0.0.1:8010/api/auth/demo-login',
    data=b'{}',
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(login_req, timeout=10) as resp:
    data = json.loads(resp.read().decode())
    token = data.get('token')
    cookie = resp.headers.get('set-cookie')

with open('ai/document_fixtures/metformin_prescription.png', 'rb') as f:
    file_bytes = f.read()

boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
parts = []
parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="synthetic-metformin-prescription.png"\r\nContent-Type: image/png\r\n\r\n'.encode('latin1'))
parts.append(file_bytes)
parts.append(f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="document_type"\r\n\r\nprescription\r\n--{boundary}--\r\n'.encode('latin1'))
body = b''.join(parts)

req = urllib.request.Request(
    'http://127.0.0.1:8010/api/sessions/50df067e-fdbc-4890-8126-dd0f2504f0e9/documents',
    data=body,
    headers={
        'Authorization': f'Bearer {token}',
        'Cookie': cookie,
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    }
)

t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        print(f"Direct backend status: {resp.status} in {time.time() - t0:.2f}s")
        print("Response:", resp.read().decode())
except Exception as e:
    print(f"Direct backend error after {time.time() - t0:.2f}s: {e}")

# Now test via Vite proxy port 5175!
req_vite = urllib.request.Request(
    'http://127.0.0.1:5175/api/sessions/50df067e-fdbc-4890-8126-dd0f2504f0e9/documents',
    data=body,
    headers={
        'Authorization': f'Bearer {token}',
        'Cookie': cookie,
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    }
)

t1 = time.time()
try:
    with urllib.request.urlopen(req_vite, timeout=60) as resp:
        print(f"Vite proxy status: {resp.status} in {time.time() - t1:.2f}s")
        print("Response:", resp.read().decode())
except Exception as e:
    print(f"Vite proxy error after {time.time() - t1:.2f}s: {e}")
