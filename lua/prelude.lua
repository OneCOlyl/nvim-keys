-- nvim-keys: loaded via --cmd BEFORE the user config.
--
-- Wraps keymap registration so we can tell which file owns every mapping.
-- Without this, mappings with a string rhs are unattributable: their `sid`
-- always points at init.lua, because required Lua modules do not get their
-- own script id.

_G.__nvim_keys_origins = {}

--- Capture the call chain, not just one file: mappings are often registered
--- through a wrapper (snacks.util.set_keymap, lazy.nvim's keys handler,
--- which-key), and the real owner sits further up the stack.
local function stack(start)
  local out = {}
  for level = start, start + 8 do
    local info = debug.getinfo(level, "Sl")
    if not info then break end
    local src = info.source or ""
    if src ~= "" and src ~= "=[C]" then
      out[#out + 1] = { source = (src:gsub("^@", "")), line = info.currentline or 0 }
    end
  end
  return out
end

local function record(modes, lhs, frames)
  if not frames or #frames == 0 then return end
  if type(modes) == "string" then modes = { modes } end
  if type(modes) ~= "table" then return end
  for _, m in ipairs(modes) do
    if m == "" then m = "n" end
    _G.__nvim_keys_origins[m .. "\0" .. tostring(lhs)] = frames
  end
end

-- vim.keymap.set calls nvim_set_keymap internally, so while an outer call is
-- running we mute the inner wrappers — otherwise every mapping would be
-- attributed to the runtime module vim/keymap.lua.
local inside = false

local orig_set = vim.keymap.set
vim.keymap.set = function(mode, lhs, rhs, opts)
  if not inside then
    pcall(record, mode, lhs, stack(3))
  end
  inside = true
  local ok, res = pcall(orig_set, mode, lhs, rhs, opts)
  inside = false
  if not ok then error(res, 0) end
  return res
end

local orig_api = vim.api.nvim_set_keymap
vim.api.nvim_set_keymap = function(mode, lhs, rhs, opts)
  if not inside then
    pcall(record, mode, lhs, stack(3))
  end
  return orig_api(mode, lhs, rhs, opts)
end

local orig_buf = vim.api.nvim_buf_set_keymap
vim.api.nvim_buf_set_keymap = function(buf, mode, lhs, rhs, opts)
  if not inside then
    pcall(record, mode, lhs, stack(3))
  end
  return orig_buf(buf, mode, lhs, rhs, opts)
end
