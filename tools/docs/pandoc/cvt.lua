-- Pandoc Lua filter used by tools/docs/md2tex.py (GFM -> project LaTeX).
-- Metadata keys (passed with -M): cvt-book, cvt-kind, cvt-slug, cvt-level,
-- cvt-pathmap, cvt-marks, cvt-src, cvt-tracked, cvt-sections-out, cvt-warn-out, cvt-record.

local C = {}          -- configuration read from metadata
local warnings = {}   -- list of {type, detail}
local labels = {}     -- heading id (cleaned) -> label for this document
local sections = {}   -- rows for the sidecar
local pathmap = {}    -- old_path -> label
local tracked = { files = {}, dirs = {} }
local target_ids = {} -- cache: repo path -> {id set, first id}

local function warn(kind, detail)
  warnings[#warnings + 1] = { kind, (detail or ''):gsub('[\t\r\n]+', ' ') }
end

local function meta_str(m, key)
  local v = m[key]
  if v == nil then return nil end
  return pandoc.utils.stringify(v)
end

-- ---------------------------------------------------------------- paths
local function normpath(p)
  local out = {}
  for part in p:gmatch('[^/]+') do
    if part == '..' then
      if #out > 0 then out[#out] = nil end
    elseif part ~= '.' then
      out[#out + 1] = part
    end
  end
  return table.concat(out, '/')
end

local function dirname(p)
  return p:match('^(.*)/[^/]*$') or ''
end

local function load_lines(path, fn)
  local f = io.open(path, 'r')
  if not f then return end
  for line in f:lines() do fn((line:gsub('\r$', ''))) end
  f:close()
end

local MARKS = {}  -- UTF-8 character -> LaTeX replacement
local load_marks   -- defined with the pictograph table below

local function load_config(meta)
  C.book = meta_str(meta, 'cvt-book') or 'cr'
  C.kind = meta_str(meta, 'cvt-kind') or 'inv'
  C.slug = meta_str(meta, 'cvt-slug') or 'doc'
  C.level = meta_str(meta, 'cvt-level') or 'chapter'
  C.src = meta_str(meta, 'cvt-src') or ''
  C.record = meta_str(meta, 'cvt-record') == '1'
  C.tables = meta_str(meta, 'cvt-tables') or 'auto'
  C.table_debug = meta_str(meta, 'cvt-table-debug') == '1'
  C.sections_out = meta_str(meta, 'cvt-sections-out')
  C.warn_out = meta_str(meta, 'cvt-warn-out')
  C.marks = meta_str(meta, 'cvt-marks')
  if not C.marks or C.marks == '' then
    local here = (PANDOC_SCRIPT_FILE or ''):match('^(.*)[/\\][^/\\]*$')
    if here then C.marks = here .. '/marks.tsv' end
  end
  load_marks(C.marks)
  C.base = C.book .. ':' .. C.kind .. ':' .. C.slug
  local pm = meta_str(meta, 'cvt-pathmap')
  if pm and pm ~= '' then
    local first = true
    load_lines(pm, function(line)
      if first then first = false; return end
      local a, _, c = line:match('^([^\t]*)\t([^\t]*)\t([^\t]*)')
      if a and a ~= '' then pathmap[a] = c end
    end)
  end
  local tr = meta_str(meta, 'cvt-tracked')
  if tr and tr ~= '' then
    load_lines(tr, function(line)
      if line ~= '' then
        tracked.files[line] = true
        local d = dirname(line)
        while d ~= '' and not tracked.dirs[d] do
          tracked.dirs[d] = true
          d = dirname(d)
        end
      end
    end)
  end
end

-- ------------------------------------------------------------- headings
local function clean_id(id)
  local s = id:lower():gsub('[^a-z0-9%-]', '-'):gsub('%-+', '-'):gsub('^%-', ''):gsub('%-$', '')
  return s
end

-- Assign unique cleaned ids to the headers of a block list.
-- Returns list of ids (one per Header, in order).
local function heading_ids(blocks)
  local seen, ids, n = {}, {}, 0
  for _, b in ipairs(blocks) do
    if b.t == 'Header' then
      n = n + 1
      local base = clean_id(b.identifier)
      if base == '' then base = 'sec' end
      local id, k = base, 1
      while seen[id] do
        k = k + 1
        id = base .. '-' .. k
      end
      seen[id] = true
      ids[#ids + 1] = id
    end
  end
  return ids
end

local function section_number(title)
  local t = title:gsub('^%s+', '')
  t = t:gsub('^§%s*', '')
  local num = t:match('^(%d+[%.%d]*)%f[%s\0]')
  if not num then
    num = t:match('^(%u%.%d[%.%d]*)%f[%s\0]')
  end
  if not num then return nil end
  num = num:gsub('%.+$', '')
  local first = tonumber(num:match('^%d+'))
  if first and first >= 1900 then return nil end
  return num
end

local function plain_title(inlines)
  return (pandoc.utils.stringify(inlines):gsub('%s+', ' '):gsub('^ ', ''):gsub(' $', ''))
end

local function pass_headings(doc)
  load_config(doc.meta)
  local ids = heading_ids(doc.blocks)
  local maxlevel = (C.level == 'section') and 4 or 5
  local first_level
  local out, hi = {}, 0
  local forced   -- value of a <!-- cvt-table: ... --> line, for the next table
  for _, b in ipairs(doc.blocks) do
    local mode = b.t == 'RawBlock' and b.format == 'html'
      and b.text:match('^%s*<!%-%-%s*cvt%-table:%s*(%a+)%s*%-%->%s*$')
    if mode then
      if mode == 'rows' or mode == 'long' or mode == 'auto' then
        forced = mode
      else
        warn('bad-table-mode', mode)
      end
    elseif b.t == 'Table' then
      if forced then b.attr.attributes['cvt-table'] = forced; forced = nil end
      out[#out + 1] = b
    elseif b.t == 'Header' then
      hi = hi + 1
      local level, label
      if hi == 1 then
        first_level = b.level
        level = 1
        label = C.base
      else
        level = b.level - (first_level - 1)
        if level < 2 then level = 2 end
        if level > maxlevel then level = maxlevel end
        label = C.base .. ':' .. ids[hi]
      end
      labels[ids[hi]] = label
      local title = plain_title(b.content)
      local num = section_number(title)
      if num then
        sections[#sections + 1] = num .. '\t' .. label .. '\t' .. title:gsub('\t', ' ')
      end
      out[#out + 1] = pandoc.Header(level, b.content, pandoc.Attr('', {}, {}))
      out[#out + 1] = pandoc.RawBlock('latex', '\\label{' .. label .. '}')
    else
      out[#out + 1] = b
    end
  end
  if hi == 0 then warn('no-heading', C.src) end
  doc.blocks = out
  return doc
end

-- ---------------------------------------------------------------- emoji
-- The pictograph table is tools/docs/pandoc/marks.tsv. prose_preserve.py reads
-- the same file, so both tools agree on every mapping.
local seen_picto = {}   -- unknown pictographs already reported for this file

function load_marks(path)
  if not path or path == '' then return end
  load_lines(path, function(line)
    if line:sub(1, 1) == '#' or line == '' then return end
    local cp, tex = line:match('^(%x+)\t([^\t]*)')
    if cp and tex then MARKS[utf8.char(tonumber(cp, 16))] = tex end
  end)
end

-- Code points that are pictographs and have no glyph in the book fonts.
-- Real text symbols with a glyph in the fallback font are not pictographs:
-- the check mark U+2713, the ballot boxes U+2610 to U+2612, the crosses U+2717
-- and U+2718.
local function is_picto(cp)
  if cp == 0x2713 or (cp >= 0x2610 and cp <= 0x2612) or cp == 0x2717 or cp == 0x2718 then
    return false
  end
  return (cp >= 0x1F000 and cp <= 0x1FAFF) or (cp >= 0x2600 and cp <= 0x27BF)
    or (cp >= 0x2B50 and cp <= 0x2B55) or (cp >= 0x231A and cp <= 0x231B)
    or (cp >= 0x23E9 and cp <= 0x23FA) or cp == 0x2B1B or cp == 0x2B1C or cp == 0x2139
end

local function unknown_picto(cp)
  local ch = utf8.char(cp)
  if not seen_picto[cp] then
    seen_picto[cp] = true
    warn('pictograph', string.format('U+%04X %s in %s mapped to notemark', cp, ch, C.src))
  end
end

local VS16 = 0xFE0F

local function str_emoji(el)
  local s = el.text
  if not s:find('[\xE2\xEF\xF0]') then return nil end
  local out, run, hit = {}, {}, false
  for _, cp in utf8.codes(s) do
    local ch = utf8.char(cp)
    local tex = MARKS[ch]
    if cp == VS16 then
      hit = true
    elseif tex or is_picto(cp) then
      hit = true
      if not tex then unknown_picto(cp); tex = '\\notemark{}' end
      if #run > 0 then out[#out + 1] = pandoc.Str(table.concat(run)); run = {} end
      out[#out + 1] = pandoc.RawInline('latex', tex)
    else
      run[#run + 1] = ch
    end
  end
  if not hit then return nil end
  if #run > 0 then out[#out + 1] = pandoc.Str(table.concat(run)) end
  return out
end

-- A long word with slashes or underscores, such as a path, a list of names or a
-- register name, may break after a slash or an underscore.
local function str_slash(el)
  local s = el.text
  if #s < 10 or not s:find('[/_]') then return nil end
  local out, pos = {}, 1
  while true do
    local i = s:find('[/_]', pos)
    if not i or i == #s then break end
    out[#out + 1] = pandoc.Str(s:sub(pos, i))
    out[#out + 1] = pandoc.RawInline('latex', '\\allowbreak{}')
    pos = i + 1
  end
  if #out == 0 then return nil end
  out[#out + 1] = pandoc.Str(s:sub(pos))
  return out
end

-- Code spans and code blocks keep their characters (the class prints the
-- known marks), but an unknown pictograph there is reported too.
local function check_code_pictographs(text)
  if not text:find('[\xE2\xF0]') then return end
  for _, cp in utf8.codes(text) do
    if is_picto(cp) and not MARKS[utf8.char(cp)] then unknown_picto(cp) end
  end
end

-- ----------------------------------------------------------- inline code
local function safe_arg(text)
  if text == '' then return false end
  if text:find('[^\32-\126]') then return false end
  if text:find('[%s\\{}%%#&~%^%$"`|\']') then return false end
  return true
end

local TT_ESCAPE = {
  ['\\'] = '\\textbackslash{}', ['{'] = '\\{', ['}'] = '\\}', ['%'] = '\\%',
  ['#'] = '\\#', ['&'] = '\\&', ['_'] = '\\_', ['$'] = '\\$',
  ['^'] = '\\textasciicircum{}', ['~'] = '\\textasciitilde{}', [' '] = '\\ ',
}
local TT_BREAK = { ['/'] = true, ['_'] = true, ['.'] = true, ['-'] = true,
  [','] = true, ['='] = true, [':'] = true, ['+'] = true }

-- Monospace text with escapes. With brk, a line may break after / _ . - , = : and +,
-- so a long path or command wraps in a narrow column. Strike-through text passes
-- brk = false because ulem cannot hold the break macro.
local function tex_escape_tt(text, brk)
  local out = {}
  for ch in text:gmatch('[%z\1-\127\194-\244][\128-\191]*') do
    out[#out + 1] = TT_ESCAPE[ch] or ch
    if brk and TT_BREAK[ch] then out[#out + 1] = '\\allowbreak{}' end
  end
  return table.concat(out)
end

local function repo_path_exists(text)
  local t = text:gsub('^%./', '')
  if tracked.files[t] then return true end
  local base = t:match('^(.-)/$')
  if base and (tracked.dirs[base] or tracked.files[base]) then return true end
  if tracked.dirs[t] then return t:find('/') ~= nil end
  local p = t:match('^(.-):%d+%-?%d*$')
  if p and tracked.files[p] then return true end
  return false
end

local function make_code(text)
  if safe_arg(text) and text:find('/') and repo_path_exists(text) then
    return pandoc.RawInline('latex', '\\src{' .. text .. '}')
  end
  if safe_arg(text) and not text:find('/') and tracked.files[text] and text:find('%.') then
    return pandoc.RawInline('latex', '\\src{' .. text .. '}')
  end
  if safe_arg(text) then
    return pandoc.RawInline('latex', '\\code{' .. text .. '}')
  end
  return pandoc.RawInline('latex', '\\texttt{' .. tex_escape_tt(text, true) .. '}')
end

local function inline_code(el)
  check_code_pictographs(el.text)
  return make_code(el.text)
end

-- ----------------------------------------------------------------- links
local function ids_of_file(path)
  if target_ids[path] ~= nil then return target_ids[path] end
  local result = false
  local f = io.open(path, 'r')
  if f then
    local text = f:read('a')
    f:close()
    local ok, doc = pcall(pandoc.read, text, 'gfm')
    if ok then
      local ids = heading_ids(doc.blocks)
      local set = {}
      for _, id in ipairs(ids) do set[id] = true end
      result = { set = set, first = ids[1] }
    end
  end
  target_ids[path] = result
  return result
end

local function with_ref(content, ref_tex)
  local out = pandoc.Inlines(content)
  out:insert(pandoc.RawInline('latex', ' (' .. ref_tex .. ')'))
  return out
end

local function same_text(content, target)
  local txt = pandoc.utils.stringify(content):gsub('^%./', '')
  local t = target:gsub('^%./', '')
  return txt == t or txt == (t:match('([^/]+)$') or t)
end

local function link_filter(el)
  local target = el.target
  if target:match('^[%a][%w+.-]*:') or target:match('^//') then return nil end
  local path, anchor = target:match('^([^#]*)#(.*)$')
  if not path then path, anchor = target, nil end
  if path == '' then
    if not anchor then return nil end
    local id = clean_id(anchor)
    local label = labels[id]
    if label then return with_ref(el.content, '\\cref{' .. label .. '}') end
    warn('unresolved-anchor', '#' .. anchor)
    return el.content
  end
  local resolved
  if path:sub(1, 1) == '/' then
    resolved = normpath(path)
  else
    resolved = normpath(dirname(C.src) .. '/' .. path)
  end
  if resolved:match('%.md$') then
    local label = pathmap[resolved]
    if label then
      if anchor and anchor ~= '' then
        local info = ids_of_file(resolved)
        local id = clean_id(anchor)
        if info and info.set[id] then
          if id ~= info.first then label = label .. ':' .. id end
        else
          warn('unresolved-anchor', resolved .. '#' .. anchor)
        end
      end
      return with_ref(el.content, '\\cref{' .. label .. '}')
    end
    warn('unmapped-md-link', resolved)
  end
  local src = make_code(resolved)
  if same_text(el.content, path) or same_text(el.content, resolved) then return src end
  local out = pandoc.Inlines(el.content)
  out:insert(pandoc.RawInline('latex', ' ('))
  out:insert(src)
  out:insert(pandoc.RawInline('latex', ')'))
  return out
end

local function image_filter(el)
  warn('image', el.src)
  local out = pandoc.Inlines(el.caption)
  out:insert(pandoc.RawInline('latex', ' ('))
  out:insert(make_code(el.src))
  out:insert(pandoc.RawInline('latex', ')'))
  return out
end

local function strikeout(el)
  local out = pandoc.Inlines({ pandoc.RawInline('latex', '\\sout{') })
  -- ulem cannot carry the expl3-based \code and \src macros: use plain \texttt inside
  local inner = el.content:walk({
    Code = function(c)
      return pandoc.RawInline('latex', '\\texttt{' .. tex_escape_tt(c.text) .. '}')
    end,
  })
  out:extend(inner)
  out:insert(pandoc.RawInline('latex', '}'))
  return out
end

-- ------------------------------------------------------------------ html
local KNOWN_HTML = {}
for w in ([[br p div span b i u em strong a sub sup details summary code pre table thead
  tbody tr td th ul ol li img hr h1 h2 h3 h4 h5 h6 center font kbd small mark dl dt dd
  blockquote picture source svg style script]]):gmatch('%S+') do KNOWN_HTML[w] = true end

local function is_real_tag(name)
  return name == name:lower() and KNOWN_HTML[name] == true
end

local function html_to_text(text)
  text = text:gsub('<!%-%-.-%-%->', function(c)
    warn('html-comment', c:sub(1, 80))
    return ''
  end)
  local res = text:gsub('(</?)([%a][%w%-]*)([^>]*>)', function(open, name, rest)
    if is_real_tag(name) then
      if name == 'br' then return '\n' end
      warn('html-tag', open .. name .. '>')
      return ''
    end
    return nil
  end)
  return res
end

local function raw_inline(el)
  if el.format ~= 'html' then return nil end
  local t = el.text
  if t:match('^<!%-%-') then
    warn('html-comment', t:sub(1, 80))
    return {}
  end
  local name = t:match('^</?([%a][%w%-]*)')
  if name and name == 'br' then return pandoc.LineBreak() end
  if name and is_real_tag(name) then
    warn('html-tag', t)
    return {}
  end
  return pandoc.Str(t)
end

local function text_inlines(text)
  local out = pandoc.Inlines({})
  local first = true
  for line in (text .. '\n'):gmatch('(.-)\n') do
    line = line:gsub('^%s+', ''):gsub('%s+$', '')
    if line ~= '' then
      if not first then out:insert(pandoc.SoftBreak()) end
      first = false
      local firstw = true
      for w in line:gmatch('%S+') do
        if not firstw then out:insert(pandoc.Space()) end
        firstw = false
        out:insert(pandoc.Str(w))
      end
    end
  end
  return out
end

local function raw_block(el)
  if el.format ~= 'html' then return nil end
  local text = html_to_text(el.text)
  local inl = text_inlines(text)
  if #inl == 0 then return {} end
  return pandoc.Para(inl)
end

-- ----------------------------------------------------------- code blocks
local LANG = {
  verilog = 'Verilog', systemverilog = 'Verilog', sv = 'Verilog', v = 'Verilog',
  python = 'Python', py = 'Python',
  tcl = 'tcl', sdc = 'tcl', upf = 'tcl',
  make = 'make', makefile = 'make',
  bash = 'bash', sh = 'bash', shell = 'bash', console = 'bash',
}

local function nlines(s)
  local n = 1
  for _ in s:gmatch('\n') do n = n + 1 end
  return n
end

-- listings typesets a non-ASCII character before the text that precedes it under
-- LuaTeX (box-drawing lines, arrows). A block with such a character therefore uses
-- the textblock environment (fancyvrb), which keeps the order and the columns.
local function code_block(el)
  local lang = (el.classes[1] or ''):lower()
  local text = el.text
  check_code_pictographs(text)
  if lang == 'log' or (lang == 'text' and nlines(text) > 40) then
    return pandoc.RawBlock('latex', '\\begin{logblock}\n' .. text .. '\n\\end{logblock}')
  end
  local caption = (lang == 'mermaid') and 'Diagram source (Mermaid)' or nil
  if text:find('[\x80-\xFF]') then
    local head = caption and ('\\cvtcaption{' .. caption .. '}\n') or ''
    return pandoc.RawBlock('latex', head .. '\\begin{textblock}\n' .. text .. '\n\\end{textblock}')
  end
  local opts = '[language={}]'
  if caption then
    opts = '[language={},caption={' .. caption .. '}]'
  elseif LANG[lang] then
    opts = '[language=' .. LANG[lang] .. ']'
  end
  return pandoc.RawBlock('latex', '\\begin{lstlisting}' .. opts .. '\n' .. text .. '\n\\end{lstlisting}')
end

-- ---------------------------------------------------------------- tables
-- Width of a block in characters. By now inline code is a raw \code or \texttt macro,
-- which stringify does not see; monospace text is also wider than body text.
local function block_len(b)
  local n = 0
  local s = pandoc.utils.stringify(b)
  n = n + (utf8.len(s) or #s)
  b:walk({
    RawInline = function(r)
      if r.format == 'latex' then
        local arg = r.text:match('^\\%a+{(.*)}$')
        if arg then
          arg = arg:gsub('\\allowbreak{}', '')
          n = n + math.ceil(#arg * 1.25)
        end
      end
    end,
  })
  return n
end

local function cell_len(cell)
  local n = 0
  for _, b in ipairs(cell.contents) do n = n + block_len(b) end
  return n
end

-- GFM tables carry no width information, so pandoc would emit plain l/r/c
-- columns that never wrap. Give wide tables proportional column widths.
local function set_widths(el)
  local ncol = #el.colspecs
  local nat = {}
  for i = 1, ncol do nat[i] = 4 end
  local function scan(rows)
    for _, row in ipairs(rows) do
      for i, cell in ipairs(row.cells) do
        if i <= ncol then
          local l = cell_len(cell)
          if l > nat[i] then nat[i] = l end
        end
      end
    end
  end
  scan(el.head.rows)
  for _, body in ipairs(el.bodies) do scan(body.body) end
  local raw = 0
  for i = 1, ncol do raw = raw + nat[i] + 2 end
  if raw <= 72 then return raw end
  local total = 0
  for i = 1, ncol do
    nat[i] = math.min(nat[i], 60)
    total = total + nat[i] + 2
  end
  local ws, sum = {}, 0
  for i = 1, ncol do
    ws[i] = math.max((nat[i] + 2) / total, 0.05)
    sum = sum + ws[i]
  end
  local cs = {}
  for i = 1, ncol do
    cs[i] = { el.colspecs[i][1], ws[i] / sum * 0.98 }
  end
  el.colspecs = cs
  return raw
end

-- Row height estimate. A longtable cannot break a row across pages, so a row that is
-- taller than the page makes longtable fail (an overfull box in the output routine,
-- and an endless loop in some TeX Live versions). The estimate is in points: for each
-- cell, the lines its text needs in the column width, times the baseline skip; the row
-- is as tall as its tallest cell. Page numbers are for A4 with 25 mm margins; a
-- landscape page swaps width and height. FONT is {size, baseline skip} per table size.
local PAGE_W, PAGE_H = 455, 703
local FONT = { normal = { 10.95, 13.6 }, small = { 10, 12 }, footnotesize = { 9, 11 } }
local CHAR_EM = 0.5        -- mean character width in em, with the wrap loss of ragged text
local ROW_LIMIT = 0.60     -- a row taller than this share of the page text height
local TABCOLSEP = { normal = 6, small = 4, footnotesize = 3 }

-- Estimated height in points of every body row, for the given size and orientation.
local function row_heights(el, size, landscape)
  local fs, skip = FONT[size][1], FONT[size][2]
  local linewidth = landscape and PAGE_H or PAGE_W
  local ncol = #el.colspecs
  local usable = linewidth - 2 * TABCOLSEP[size] * ncol
  local heights = {}
  for _, body in ipairs(el.bodies) do
    for _, row in ipairs(body.body) do
      local tallest = 1
      for i, cell in ipairs(row.cells) do
        local w = el.colspecs[i] and el.colspecs[i][2]
        if type(w) == 'number' and w > 0 then
          local cpl = math.max(4, math.floor(w * usable / (fs * CHAR_EM)))
          local lines = 0
          for _, b in ipairs(cell.contents) do
            lines = lines + math.max(1, math.ceil(block_len(b) / cpl)) + 0.5
          end
          if lines > tallest then tallest = lines end
        end
      end
      heights[#heights + 1] = tallest * skip + 4
    end
  end
  return heights
end

-- Render blocks to LaTeX text. A code block in a cell is converted first.
local function render_blocks(blocks)
  local doc = pandoc.Pandoc(blocks):walk({ CodeBlock = code_block })
  return (pandoc.write(doc, 'latex'):gsub('%s+$', ''))
end

local function render_inlines(inlines)
  return render_blocks({ pandoc.Plain(inlines) })
end

local function cell_plain(cell)
  return pandoc.utils.stringify(pandoc.Blocks(cell.contents)):gsub('%s+', ' '):gsub('^ ', ''):gsub(' $', '')
end

-- A table as a list of row blocks: no column, so a row breaks across pages freely.
-- Each row has a bold title (the first cell with its header) and one entry per other
-- column, "Header: content". A first cell that is long becomes "Row N" and an entry.
local function row_blocks(el)
  local headers = {}
  for _, hrow in ipairs(el.head.rows) do
    for i, cell in ipairs(hrow.cells) do
      headers[i] = headers[i] or render_blocks(cell.contents)
    end
  end
  local function head(i) return headers[i] or '' end
  local names = {}
  for i = 1, #el.colspecs do
    if head(i) ~= '' then names[#names + 1] = head(i) end
  end
  local out = {
    pandoc.RawBlock('latex', '\\begin{rowtable}'),
    pandoc.RawBlock('latex', '\\rowcolumns{' .. table.concat(names, ', ') .. '}'),
  }
  local n = 0
  for _, body in ipairs(el.bodies) do
    for _, row in ipairs(body.body) do
      n = n + 1
      local first = row.cells[1]
      local from = 1
      local title
      if first and #first.contents == 1 and cell_len(first) <= 40
          and first.contents[1].t == 'Plain' and cell_plain(first) ~= '' then
        local h = head(1)
        local sep = h:find('%w') and ': ' or ' '
        title = (h ~= '' and ('\\textbf{' .. h .. '}' .. sep) or '') .. render_blocks(first.contents)
        from = 2
      else
        title = 'Row ' .. n
      end
      out[#out + 1] = pandoc.RawBlock('latex', '\\rowtitle{' .. title .. '}')
      for i = from, #row.cells do
        local cell = row.cells[i]
        if #cell.contents > 0 then
          out[#out + 1] = pandoc.RawBlock('latex', '\\begin{rowcell}{' .. head(i) .. '}')
          for _, b in ipairs(cell.contents) do out[#out + 1] = b end
          out[#out + 1] = pandoc.RawBlock('latex', '\\end{rowcell}')
        end
      end
    end
  end
  out[#out + 1] = pandoc.RawBlock('latex', '\\end{rowtable}')
  return out
end

-- A wide table gets a smaller font and less column padding. A table with 7 or more
-- columns goes on a landscape page, where the linewidth is the page height.
-- A table that would have a row taller than ROW_LIMIT of the page becomes row blocks
-- (see row_blocks). A comment line before the table forces the form:
--   <!-- cvt-table: rows -->   or   <!-- cvt-table: long -->
-- The same choice for a whole document: md2tex.py --tables {auto,rows,long}.
local function table_filter(el)
  local raw = set_widths(el)
  local size = ''
  if raw > 200 then
    size = '\\footnotesize\\setlength{\\tabcolsep}{3pt}'
  elseif raw > 120 then
    size = '\\small\\setlength{\\tabcolsep}{4pt}'
  end
  local landscape = #el.colspecs >= 7
  local mode = el.attr.attributes['cvt-table'] or C.tables
  local est = 0
  if raw > 72 then
    local name = (raw > 200 and 'footnotesize') or ((raw > 120 or landscape) and 'small') or 'normal'
    for _, h in ipairs(row_heights(el, name, landscape)) do
      if h > est then est = h end
    end
  end
  local limit = ROW_LIMIT * (landscape and PAGE_W or PAGE_H)
  if C.table_debug then
    warn('table-estimate', string.format('%s: %d columns, tallest row %.0f pt, %.0f%% of the page, %s',
      C.src, #el.colspecs, est, est / (landscape and PAGE_W or PAGE_H) * 100,
      landscape and 'landscape' or 'portrait'))
  end
  if mode == 'rows' or (mode ~= 'long' and est > limit) then
    return row_blocks(el)
  end
  if landscape then
    if size == '' then size = '\\small\\setlength{\\tabcolsep}{4pt}' end
    return {
      pandoc.RawBlock('latex', '\\begin{landscape}\n' .. size),
      el,
      pandoc.RawBlock('latex', '\\end{landscape}'),
    }
  end
  if size ~= '' then
    return {
      pandoc.RawBlock('latex', '{' .. size),
      el,
      pandoc.RawBlock('latex', '}'),
    }
  end
  return el
end

-- ---------------------------------------------------------------- record
local function pass_final(doc)
  if C.record then
    local out, inside, seen_header = {}, false, false
    local function close()
      if inside then
        out[#out + 1] = pandoc.RawBlock('latex', '\\end{record}')
        inside = false
      end
    end
    for _, b in ipairs(doc.blocks) do
      if b.t == 'Header' then
        close()
        seen_header = true
        out[#out + 1] = b
      elseif seen_header and b.t == 'RawBlock' and b.text:match('^\\label{') and not inside then
        out[#out + 1] = b
      else
        if seen_header and not inside then
          out[#out + 1] = pandoc.RawBlock('latex', '\\begin{record}')
          inside = true
        end
        out[#out + 1] = b
      end
    end
    close()
    doc.blocks = out
  end
  if C.sections_out and C.sections_out ~= '' then
    local f = io.open(C.sections_out, 'w')
    if f then
      f:write('number\tlabel\ttitle\n')
      for _, row in ipairs(sections) do f:write(row, '\n') end
      f:close()
    end
  end
  if C.warn_out and C.warn_out ~= '' then
    local f = io.open(C.warn_out, 'w')
    if f then
      for _, w in ipairs(warnings) do f:write(w[1], '\t', w[2], '\n') end
      f:close()
    end
  end
  return doc
end

return {
  { Pandoc = pass_headings },
  { Link = link_filter, Image = image_filter },
  { Str = str_emoji, Strikeout = strikeout },
  { Str = str_slash },
  { Code = inline_code },
  { RawInline = raw_inline, RawBlock = raw_block },
  { CodeBlock = code_block, Table = table_filter },
  { Pandoc = pass_final },
}
