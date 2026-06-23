const fs = require('fs');
const code = fs.readFileSync('static/app.js', 'utf8');

// Find the material_generation handler in runSavedFlow
const idx = code.indexOf('low.scriptType === "material_generation")');
if (idx < 0) {
    console.log('NOT FOUND');
    process.exit(1);
}

// Show the structure around this area with line numbers
const start = idx - 100;
const end = Math.min(code.length, idx + 5000);
const chunk = code.substring(start, end);

// Count lines from the start of the file
const beforeLines = code.substring(0, start).split('\n').length;
console.log('Starting at approx line', beforeLines);

const lines = chunk.split('\n');
for (let i = 0; i < lines.length && i < 80; i++) {
    const lineNum = beforeLines + i;
    const line = lines[i];
    console.log(lineNum + ':' + line.substring(0, 150));
}
