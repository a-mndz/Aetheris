import re

with open('recovered_rate_limiter.txt', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.split('\n')
parsed_lines = []
for line in lines:
    m = re.match(r'^(\d+):\s(.*)$', line)
    if m:
        parsed_lines.append(m.group(2))

with open('api_gateway/rate_limiter.py', 'r', encoding='utf-8') as f:
    old_lines = f.read().split('\n')

idx = -1
for i, line in enumerate(old_lines):
    if line.startswith('# ── Async API Gateway'):
        idx = i
        break

if idx != -1:
    combined = parsed_lines + old_lines[idx:]
    with open('api_gateway/rate_limiter.py', 'w', encoding='utf-8') as f:
        f.write('\n'.join(combined))
    print('Successfully combined! Total lines:', len(combined))
else:
    print('Failed to find AsyncAPIGateway')
