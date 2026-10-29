// Parse submitted configuration and source without evaluating it.
const ts = require(require.resolve('typescript', { paths: [process.env.VOTING_VERIFIER_DEPS || '/root/voting-verifier'] }));
let input = '';
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  const files = JSON.parse(input);
  const result = { imports: [], configs: {}, aliases: {}, unresolved: [] };
  for (const [name, text] of Object.entries(files)) {
    if (/\.(?:json|jsonc)$/.test(name)) {
      try {
        result.configs[name] = JSON.parse(text);
        continue;
      } catch {}
      const parsed = ts.parseConfigFileTextToJson(name, text);
      if (parsed.error) result.unresolved.push(`${name}: invalid JSON configuration`);
      else result.configs[name] = parsed.config;
      continue;
    }
    const tree = ts.createSourceFile(name, text, ts.ScriptTarget.Latest, true);
    function literal(node) { return node && (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) ? node.text : undefined; }
    function visit(node) {
      if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
        result.imports.push({ owner: name, specifier: literal(node.moduleSpecifier) });
      }
      if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword || node.expression.getText(tree) === 'require')) {
        const specifier = literal(node.arguments[0]);
        if (specifier === undefined) result.unresolved.push(`${name}: computed import at line ${tree.getLineAndCharacterOfPosition(node.pos).line + 1}`);
        else result.imports.push({ owner: name, specifier });
      }
      if (ts.isCallExpression(node) && /import\.meta\.glob/.test(node.expression.getText(tree))) {
        result.unresolved.push(`${name}: import.meta.glob needs an explicit resolver`);
      }
      if (/vite\.config\./.test(name) && ts.isPropertyAssignment(node) && node.name.getText(tree) === 'alias') {
        if (!ts.isObjectLiteralExpression(node.initializer)) result.unresolved.push(`${name}: unsupported alias configuration`);
        else for (const entry of node.initializer.properties) {
          if (!ts.isPropertyAssignment(entry)) { result.unresolved.push(`${name}: computed alias`); continue; }
          const key = literal(entry.name) ?? entry.name.getText(tree);
          let value = literal(entry.initializer);
          // Accept the usual path.resolve(__dirname, './src') and URL forms without executing them.
          const match = entry.initializer.getText(tree).match(/^(?:path\.)?resolve\(__dirname,\s*['"]([^'"]+)['"]\)$/)
            || entry.initializer.getText(tree).match(/^fileURLToPath\(new URL\(['"]([^'"]+)['"],\s*import\.meta\.url\)\)$/);
          if (match) value = match[1];
          if (value === undefined || key.includes('/')) result.unresolved.push(`${name}: unsupported alias ${key}`);
          else result.aliases[key] = value;
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(tree);
  }
  process.stdout.write(JSON.stringify(result));
});
