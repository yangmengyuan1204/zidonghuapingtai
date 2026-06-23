with open('static/app.js', 'r', encoding='utf-8') as f:
    c = f.read()

idx = c.find('if (flow.scriptType === "material_generation")')
if idx >= 0:
    end = c.find('progress.update(24', idx)
    if end >= 0:
        chunk = c[idx:end+50]
        ob = chunk.count('{')
        cb = chunk.count('}')
        print('material_generation handler: open=%d close=%d balance=%d' % (ob, cb, ob-cb))

idx2 = c.find('material_generation: [')
if idx2 >= 0:
    nearby = c[idx2:idx2+300]
    ob2 = nearby.count('{')
    cb2 = nearby.count('}')
    print('SCRIPT_PARAM_SCHEMAS section: open=%d close=%d balance=%d' % (ob2, cb2, ob2-cb2))

ob_t = c.count('{')
cb_t = c.count('}')
print('Total: open=%d close=%d balance=%d' % (ob_t, cb_t, ob_t-cb_t))
