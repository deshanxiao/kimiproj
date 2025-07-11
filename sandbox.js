const { VM } = require('vm2');
const fs = require('fs');

const filePath = process.argv[2];
const timeout = parseInt(process.argv[3]) || 30000;
const output = [];
let error = null;

let code;
try {
    code = fs.readFileSync(filePath, 'utf8');
    console.log('Received code:', code);
} catch (e) {
    error = { name: e.name, message: e.message, stack: e.stack };
    console.log('Error reading file:', error);
}

const vm = new VM({
    timeout: timeout * 1000,
    sandbox: {
        console: {
            log: (...args) => {
                output.push(args.join(' '));
            }
        },
        setTimeout,
        Plotly: typeof Plotly !== 'undefined' ? Plotly : undefined,
        process: { stdin: null, stdout: process.stdout } // 提供模拟的 process 对象
    },
    require: {
        builtin: ['readline'] // 允许 readline 模块
    }
});

if (!error) {
    try {
        console.log('Starting code execution');
        vm.run(code);
        console.log('Code execution completed');
        if (vm.run('typeof Plotly !== "undefined"')) {
            console.log('Plotly detected, generating image');
            const fig = vm.run('fig || { data: [], layout: {} }');
            const img = vm.run(`Plotly.toImage(${JSON.stringify(fig)}, {format: 'png', width: 800, height: 600})`);
            fs.writeFileSync('/tmp/plot.png', img.replace(/^data:image\/png;base64,/, ''), 'base64');
        }
    } catch (e) {
        error = { name: e.name, message: e.message, stack: e.stack };
        console.log('Execution error:', error);
    }
}

console.log('__OUTPUT__:' + JSON.stringify(output));
if (error) {
    console.log('__ERROR__:' + JSON.stringify(error));
}