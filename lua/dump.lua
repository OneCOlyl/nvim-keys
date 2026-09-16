-- nvim-keys: collect every keymap of Neovim and its plugins into JSON.
--
-- Run as:
--   NVIM_KEYS_OUT=/path/out.json nvim --headless \
--     --cmd "luafile prelude.lua" -c "luafile dump.lua" -c "qa!"
--
-- Use -c, not -l: with -l Neovim skips the user config entirely.
--
-- Sources are reported as plugin names, or as one of these special keys the
-- UI localizes: $config (user config), $neovim (built-in), $other.

local MODES = { "n", "i", "v", "x", "s", "o", "t", "c" }
local MODE_NAMES = {
  n = "normal", i = "insert", v = "visual+select", x = "visual",
  s = "select", o = "operator", t = "terminal", c = "command",
}

local SRC_CONFIG = "$config"
local SRC_NEOVIM = "$neovim"
local SRC_OTHER = "$other"

local out_path = vim.env.NVIM_KEYS_OUT
  or (_G.arg and _G.arg[1])
  or (vim.fn.stdpath("cache") .. "/nvim-keys/keymaps.json")

---------------------------------------------------------------------------
-- 1. Force-load lazy.nvim plugins so their mappings actually get registered
---------------------------------------------------------------------------
local has_lazy, Config = pcall(require, "lazy.core.config")
local plugin_by_dir = {}
local lazy_plugins = {}

if has_lazy then
  for name, p in pairs(Config.plugins) do
    lazy_plugins[#lazy_plugins + 1] = name
    if p.dir then
      plugin_by_dir[vim.fs.normalize(p.dir)] = name
    end
  end
  pcall(function()
    require("lazy").load({ plugins = lazy_plugins, show = false })
  end)
end

-- Headless has no UI, so VeryLazy never fires on its own. Distributions like
-- LazyVim hang their own keymaps (and lua/config/keymaps.lua) off that event.
pcall(vim.api.nvim_exec_autocmds, "User", { pattern = "VeryLazy", modeline = false })
pcall(vim.api.nvim_exec_autocmds, "UIEnter", { modeline = false })
pcall(require, "config.keymaps")

-- let plugins finish their deferred schedule() work
vim.wait(300, function() return false end)
vim.cmd("redraw")
vim.wait(200, function() return false end)

---------------------------------------------------------------------------
-- 2. Figuring out where a mapping came from
---------------------------------------------------------------------------
local script_by_sid = {}
for _, s in ipairs(vim.fn.getscriptinfo()) do
  script_by_sid[s.sid] = s.name
end

local config_dir = vim.fs.normalize(vim.fn.stdpath("config"))
local runtime_dir = vim.fs.normalize(vim.env.VIMRUNTIME or "/usr/share/nvim/runtime")

local function clean_source(src)
  if not src then return nil end
  src = src:gsub("^@", "")
  return vim.fs.normalize(src)
end

--- @return string source name (plugin or special key), string|nil file path
local function classify(src)
  if not src or src == "" then
    return SRC_NEOVIM, nil
  end

  -- a path inside a plugin directory managed by lazy.nvim
  -- non-greedy on purpose: "/lazy/LazyVim/lua/lazy/core/…" must not yield "core"
  local lazy_root = src:match("^(.-/lazy/[^/]+)/")
  if lazy_root then
    return plugin_by_dir[lazy_root] or lazy_root:match("([^/]+)$"), src
  end

  if src:find(config_dir, 1, true) == 1 then
    return SRC_CONFIG, src
  end

  if src:find(runtime_dir, 1, true) == 1 or src:find("^vim/") or src:find("^%[") then
    return SRC_NEOVIM, src
  end

  return SRC_OTHER, src
end

---------------------------------------------------------------------------
-- 3. Real (global) keymaps
---------------------------------------------------------------------------
local items = {}
local seen = {}

local function keytrans(lhs)
  local ok, res = pcall(vim.fn.keytrans, lhs)
  if ok and res and res ~= "" then return res end
  return lhs
end

local leader = vim.g.mapleader or "\\"
local localleader = vim.g.maplocalleader or "\\"

--- Canonical form of a lhs, so "<leader>ff" and raw bytes end up identical
local function pretty_lhs(lhs)
  -- <leader> is not a termcode, nvim_replace_termcodes leaves it alone
  lhs = lhs:gsub("<[lL][eE][aA][dD][eE][rR]>", leader:gsub("%%", "%%%%"))
  lhs = lhs:gsub("<[lL][oO][cC][aA][lL][lL][eE][aA][dD][eE][rR]>", localleader:gsub("%%", "%%%%"))
  local ok, raw = pcall(vim.api.nvim_replace_termcodes, lhs, true, true, true)
  return keytrans(ok and raw or lhs)
end

local leader_pretty = keytrans(leader)

--- What the user should see: spell out a leading leader key
local function display_lhs(pretty)
  if leader_pretty ~= "" and pretty:sub(1, #leader_pretty) == leader_pretty then
    return "<leader>" .. pretty:sub(#leader_pretty + 1)
  end
  return pretty
end

-- Wrapper files: they only forward the call, the owner is higher up the stack
local WRAPPERS = {
  "/lazy%.nvim/lua/lazy/core/handler/keys%.lua",
  "/snacks%.nvim/lua/snacks/keymap%.lua",
  "/snacks%.nvim/lua/snacks/util%.lua",
  "/which%-key%.nvim/lua/which%-key/mappings%.lua",
  "/nvim%-keys/prelude%.lua",
  "/lua/prelude%.lua",
  "^vim/keymap",
  "^vim/_core",
  "^vim/shared",
}

local function is_wrapper(src)
  for _, pat in ipairs(WRAPPERS) do
    if src:find(pat) then return true end
  end
  return false
end

--- First non-wrapper frame of the recorded call chain
local function pick_frame(frames)
  if type(frames) ~= "table" then return nil end
  for _, f in ipairs(frames) do
    if f.source and not is_wrapper(f.source) then return f end
  end
  return frames[1]
end

-- origins recorded by prelude.lua at registration time
local origins = {}
for key, frames in pairs(_G.__nvim_keys_origins or {}) do
  local mode, lhs = key:match("^(.-)%z(.*)$")
  if mode then
    origins[mode .. "\0" .. pretty_lhs(lhs)] = pick_frame(frames)
  end
end

local function add(item)
  local key = item.mode .. "\0" .. item.lhs .. "\0" .. (item.buffer or "")
  if seen[key] then
    -- already known: only fill in a missing description
    local prev = seen[key]
    if (prev.desc == "" or prev.desc == nil) and item.desc and item.desc ~= "" then
      prev.desc = item.desc
    end
    return
  end
  seen[key] = item
  items[#items + 1] = item
end

local LAZY_HANDLER = "/lazy.nvim/lua/lazy/core/handler/keys.lua"

for _, mode in ipairs(MODES) do
  for _, k in ipairs(vim.api.nvim_get_keymap(mode)) do
    -- nvim_get_keymap returns lhs already readable ("<C-E>") for special keys
    -- but raw for plain ones (" "), so normalize both the same way
    local lhs = pretty_lhs(k.lhs)
    local src

    local origin = origins[mode .. "\0" .. lhs]
    if origin then src = clean_source(origin.source) end

    -- prelude missed it (or it was set from Vimscript): try the callback itself
    if (not src or src:find(LAZY_HANDLER, 1, true)) and k.callback then
      local ok, info = pcall(debug.getinfo, k.callback, "S")
      if ok and info then
        local cb_src = clean_source(info.source)
        if cb_src and not cb_src:find(LAZY_HANDLER, 1, true) then
          src = cb_src
        end
      end
    end
    if not src and k.sid and script_by_sid[k.sid] then
      src = vim.fs.normalize(script_by_sid[k.sid])
    end

    local plugin, source = classify(src)

    -- lazy.nvim wraps lazy-loaded mappings in its own handler, which says
    -- nothing about the plugin — the spec pass below fills that in
    if source and source:find(LAZY_HANDLER, 1, true) then
      plugin = nil
    end

    local rhs = k.rhs
    if (not rhs or rhs == "") and k.callback then rhs = "<lua function>" end

    add({
      mode = mode,
      mode_name = MODE_NAMES[mode] or mode,
      lhs = lhs,
      rhs = rhs or "",
      desc = k.desc or "",
      plugin = plugin,
      source = source,
      line = origin and origin.line or nil,
      pending = false,
    })
  end
end

---------------------------------------------------------------------------
-- 4. Keymaps declared in lazy.nvim specs (including not-yet-loaded plugins)
---------------------------------------------------------------------------
local function spec_modes(m)
  if type(m) == "table" then return m end
  if type(m) == "string" then return { m } end
  return { "n" }
end

--- Every key spec of a plugin: the raw spec plus the parsed handler entries.
--- p.keys holds only the last spec fragment; p._.handlers.keys holds them all.
local function plugin_keys(p)
  local list = {}

  local raw = p.keys
  if type(raw) == "function" then
    local ok, res = pcall(raw)
    raw = ok and type(res) == "table" and res or nil
  end
  if type(raw) == "table" then
    for _, k in ipairs(raw) do list[#list + 1] = k end
  end

  local handled = p._ and p._.handlers and p._.handlers.keys
  if type(handled) == "table" then
    for _, k in pairs(handled) do
      if type(k) == "table" and k.lhs then
        list[#list + 1] = { k.lhs, desc = k.desc, mode = k.mode }
      end
    end
  end

  return list
end

local GUESSED = { LazyVim = true, ["lazy.nvim"] = true, [SRC_NEOVIM] = true }

if has_lazy then
  local names = vim.tbl_keys(Config.plugins)
  -- deterministic order: several plugins may declare the same lhs,
  -- first one alphabetically wins
  table.sort(names)
  for _, name in ipairs(names) do
    local p = Config.plugins[name]
    for _, k in ipairs(plugin_keys(p)) do
      local lhs, desc, modes
      if type(k) == "string" then
        lhs, desc, modes = k, "", { "n" }
      elseif type(k) == "table" then
        lhs, desc, modes = k[1], k.desc or "", spec_modes(k.mode)
      end
      if type(lhs) == "string" and lhs ~= "" then
        for _, mode in ipairs(modes) do
          local pretty = pretty_lhs(lhs)
          local prev = seen[mode .. "\0" .. pretty .. "\0"]
          if prev then
            -- the plugin spec is the most reliable owner: it overrides guesses
            -- made from the file path
            if not prev.spec_owner and (not prev.plugin or GUESSED[prev.plugin]) then
              prev.plugin = name
              prev.spec_owner = true
            end
            if prev.desc == "" then prev.desc = desc end
          else
            add({
              mode = mode,
              mode_name = MODE_NAMES[mode] or mode,
              lhs = pretty,
              rhs = "",
              desc = desc,
              plugin = name,
              source = p.dir,
              pending = true,
            })
          end
        end
      end
    end
  end
end

---------------------------------------------------------------------------
-- 5. LazyVim LSP keymaps (buffer-local, only exist once an LSP attaches)
---------------------------------------------------------------------------
-- M.get() is deprecated and prints a warning, so read the table directly
local ok_lsp, lsp_mod = pcall(require, "lazyvim.plugins.lsp.keymaps")
local lsp_keys = ok_lsp and type(lsp_mod) == "table" and lsp_mod._keys or nil
if type(lsp_keys) == "table" then
  for _, k in ipairs(lsp_keys) do
    local lhs = type(k) == "table" and k[1] or nil
    if type(lhs) == "string" and lhs ~= "" then
      for _, mode in ipairs(spec_modes(k.mode)) do
        add({
          mode = mode,
          mode_name = MODE_NAMES[mode] or mode,
          lhs = pretty_lhs(lhs),
          rhs = "",
          desc = k.desc or "",
          plugin = "LSP (LazyVim)",
          source = "lazyvim/plugins/lsp/keymaps.lua",
          buffer = "lsp",
          pending = true,
        })
      end
    end
  end
end

---------------------------------------------------------------------------
-- 6. Finalize
---------------------------------------------------------------------------
for _, it in ipairs(items) do
  it.plugin = it.plugin or SRC_NEOVIM
  it.display = display_lhs(it.lhs)
  it.group = it.desc:sub(1, 1) == "+" -- which-key prefix group
  -- an empty desc stays empty: the UI falls back to the rhs itself and can
  -- make it readable, while "desc = rhs" would look like a real description
  it.source = it.source or ""
  it.buffer = it.buffer or ""
  it.spec_owner = nil
end

table.sort(items, function(a, b)
  if a.plugin ~= b.plugin then return a.plugin < b.plugin end
  if a.lhs ~= b.lhs then return a.lhs < b.lhs end
  return a.mode < b.mode
end)

local payload = {
  generated_at = os.time(),
  nvim_version = tostring(vim.version()),
  mapleader = leader_pretty,
  count = #items,
  keymaps = items,
}

vim.fn.mkdir(vim.fn.fnamemodify(out_path, ":h"), "p")
local fd = assert(io.open(out_path, "w"))
fd:write(vim.json.encode(payload))
fd:close()

io.stdout:write(string.format("nvim-keys: %d keymaps -> %s\n", #items, out_path))
