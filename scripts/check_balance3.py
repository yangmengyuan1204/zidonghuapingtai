with open('static/app.js', 'r', encoding='utf-8') as f:
    c = f.read()

# Check BUILTIN_FLOW_DEFINITIONS area
idx = c.find('material_generation: { id: "material_generation_builtin"')
if idx >= 0:
    nearby = c[idx-100:idx+300]
    ob = nearby.count('{')
    cb = nearby.count('}')
    print('BUILTIN_FLOW_DEFINITIONS area: open=%d close=%d balance=%d' % (ob, cb, ob-cb))

# Check flowSteps
idx2 = c.find('direct_box_to_shelf')
if idx2 >= 0:
    nearby2 = c[idx2:idx2+300]
    ob2 = nearby2.count('{')
    cb2 = nearby2.count('}')
    print('flowSteps area: open=%d close=%d balance=%d' % (ob2, cb2, ob2-cb2))

# Check sanitizeScriptVariables
idx3 = c.find('if (scriptType === "material_generation")')
if idx3 >= 0:
    nearby3 = c[idx3-50:idx3+200]
    ob3 = nearby3.count('{')
    cb3 = nearby3.count('}')
    print('sanitize material_gen area: open=%d close=%d balance=%d' % (ob3, cb3, ob3-cb3))

# Check LABEL_MAP area  
idx4 = c.find('material_generation_name:')
if idx4 >= 0:
    # Find the one in LABEL_MAP (not in runSavedFlow)
    idx_lm = c.find('renderChineseSummary')
    idx_mgn = c.find('material_generation_name:', idx_lm)
    if idx_mgn >= 0:
        nearby4 = c[idx_mgn-50:idx_mgn+200]
        ob4 = nearby4.count('{')
        cb4 = nearby4.count('}')
        print('LABEL_MAP area: open=%d close=%d balance=%d' % (ob4, cb4, ob4-cb4))

# Check builtInTypes
idx5 = c.find('"material_generation"];')
if idx5 >= 0:
    nearby5 = c[idx5-50:idx5+50]
    print('builtInTypes area: ' + repr(nearby5[:80]))
