with open('static/app.js', 'r', encoding='utf-8') as f:
    c = f.read()
opens = c.count('{')
closes = c.count('}')
print(f'Braces: {opens} open, {closes} close, balance={opens-closes}')
opens_p = c.count('(')
closes_p = c.count(')')
print(f'Parens: {opens_p} open, {closes_p} close, balance={opens_p-closes_p}')
# backtick count
bt = c.count(chr(96))
print(f'Backticks: {bt} (should be even)')
