// Dependency-free Python syntax highlighter.
// Produces plain token objects; rendering happens as React text nodes, so
// highlighted code is inert — never converted to HTML.

const KEYWORDS = new Set([
  'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def',
  'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
  'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise',
  'return', 'try', 'while', 'with', 'yield',
])

const BUILTINS = new Set([
  'print', 'len', 'range', 'int', 'float', 'str', 'list', 'dict', 'set', 'tuple',
  'enumerate', 'zip', 'map', 'filter', 'sorted', 'sum', 'min', 'max', 'abs',
  'round', 'repr', 'type', 'isinstance', 'open', 'super', 'None', 'True', 'False',
])

const SCANNER = new RegExp(
  [
    '(#[^\\n]*)',                                        // 1: comment
    '("""[\\s\\S]*?"""|\'\'\'[\\s\\S]*?\'\'\'' +
      '|"(?:\\\\.|[^"\\\\\\n])*"?|\'(?:\\\\.|[^\'\\\\\\n])*\'?)', // 2: string
    '\\b(\\d+\\.?\\d*(?:[eE][+-]?\\d+)?)\\b',            // 3: number
    '([A-Za-z_]\\w*)',                                   // 4: identifier
    '(\\s+)',                                            // 5: whitespace
    '([^\\sA-Za-z_0-9]+)',                               // 6: operator/punct
  ].join('|'),
  'g',
)

function classifyWord(word, nextChar) {
  if (KEYWORDS.has(word)) return 'kw'
  if (BUILTINS.has(word)) return 'bi'
  if (nextChar === '(') return 'fn'
  if (/^[A-Z]/.test(word)) return 'cls'
  return 'id'
}

export function tokenize(code) {
  const tokens = []
  let last = 0
  SCANNER.lastIndex = 0
  let m
  while ((m = SCANNER.exec(code)) !== null) {
    if (m.index === SCANNER.lastIndex) SCANNER.lastIndex++ // never loop on empty matches
    if (m.index > last) tokens.push({ cls: 'plain', text: code.slice(last, m.index) })
    if (m[1] !== undefined) tokens.push({ cls: 'com', text: m[1] })
    else if (m[2] !== undefined) tokens.push({ cls: 'str', text: m[2] })
    else if (m[3] !== undefined) tokens.push({ cls: 'num', text: m[3] })
    else if (m[4] !== undefined) {
      const after = code.slice(SCANNER.lastIndex).match(/^\s*\(/)
      tokens.push({ cls: classifyWord(m[4], after ? '(' : ''), text: m[4] })
    } else if (m[5] !== undefined) tokens.push({ cls: 'ws', text: m[5] })
    else tokens.push({ cls: 'op', text: m[6] })
    last = SCANNER.lastIndex
  }
  if (last < code.length) tokens.push({ cls: 'plain', text: code.slice(last) })
  return tokens
}

// Split tokens into lines: [[{cls, text}, ...], ...] (text never contains \n).
export function highlightLines(code) {
  const lines = [[]]
  for (const tok of tokenize(code || '')) {
    const parts = tok.text.split('\n')
    parts.forEach((part, i) => {
      if (i > 0) lines.push([])
      if (part) lines[lines.length - 1].push({ cls: tok.cls, text: part })
    })
  }
  return lines
}
