import re
with open(r'D:\A_zidonghuapingtai\static\full-flow.js', 'r', encoding='utf-8') as f:
    content = f.read()
opens = content.count('{')
closes = content.count('}')
print(f'Open braces: {opens}, Close braces: {closes}')
if opens != closes:
    print(f'WARNING: mismatch of {opens - closes}')
opens_p = content.count('(')
closes_p = content.count(')')
print(f'Open parens: {opens_p}, Close parens: {closes_p}')
if opens_p != closes_p:
    print(f'WARNING: mismatch of {opens_p - closes_p}')
print('Syntax check done')
