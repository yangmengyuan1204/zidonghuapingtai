import re

with open('static/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Check template literals (backticks)
templates = [i for i, ch in enumerate(content) if ch == '`']
print(f'Backtick count: {len(templates)} (should be even)')
if len(templates) % 2 != 0:
    print(f'UNEVEN! Last backtick at position {templates[-1]}')
    start = max(0, templates[-1] - 60)
    end = min(len(content), templates[-1] + 60)
    print(f'Context: {repr(content[start:end])}')

# Check for any syntax issues near our insertions
# The insert at the end of porder_bank_payment handler
idx = content.find('/api/data-scripts/porder-bank-payment')
if idx >= 0:
    # Show the structure around the insertion point
    start = max(0, idx - 100)
    # Find the closing of our inserted material_generation block
    insert_end = content.find('progress.update(24', idx)
    if insert_end >= 0:
        end = insert_end + 80
        chunk = content[start:end]
        # Show newlines only for clarity
        print('\nArea around porder_bank_payment -> material_generation insertion:')
        lines = chunk.split('\n')
        for i, line in enumerate(lines):
            print(f'{i:3d}: {line[:120]}')
