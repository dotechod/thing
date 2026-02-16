-- ============================================================
-- CC:Tweaked YouTube Music Player
-- With playlists & queue!
-- Updated for ytmusicapi backend
-- ============================================================

local SERVER = "http://159.54.173.26:3000"
local LYRIC_OFFSET = 0
local BACK_DOUBLE_TAP_TIMEOUT_MS = 1800
local AUDIO_CHUNK_SIZE = 4 * 1024
local SPEAKER_RETRY_TIMEOUT_S = 0.2

local dfpwm = require("cc.audio.dfpwm")
local allSpeakers = { peripheral.find("speaker") }
if #allSpeakers == 0 then
    printError("No speakers found!")
    return
end

local leftSpeakers = {}
local rightSpeakers = {}

local function getSpeakerName(speaker)
    local ok, name = pcall(peripheral.getName, speaker)
    if ok and type(name) == "string" then
        return name
    end
    return ""
end

local function splitSpeakersBySide(speakers)
    local entries = {}
    for _, speaker in ipairs(speakers) do
        local name = getSpeakerName(speaker)
        entries[#entries + 1] = {
            speaker = speaker,
            name = string.lower(name),
            rawName = name
        }
    end

    table.sort(entries, function(a, b)
        return a.rawName < b.rawName
    end)

    local left = {}
    local right = {}
    local unknown = {}

    for _, entry in ipairs(entries) do
        if entry.name:find("left", 1, true) then
            left[#left + 1] = entry.speaker
        elseif entry.name:find("right", 1, true) then
            right[#right + 1] = entry.speaker
        else
            unknown[#unknown + 1] = entry.speaker
        end
    end

    -- No side hints in names: split deterministic first half (left), second half (right).
    if #left == 0 and #right == 0 then
        local leftCount = math.ceil(#entries / 2)
        for i = 1, leftCount do
            left[#left + 1] = entries[i].speaker
        end
        for i = leftCount + 1, #entries do
            right[#right + 1] = entries[i].speaker
        end
        return left, right
    end

    -- If some speakers are untagged, keep channels balanced while preserving tagged sides.
    for _, speaker in ipairs(unknown) do
        if #left <= #right then
            left[#left + 1] = speaker
        else
            right[#right + 1] = speaker
        end
    end

    return left, right
end

leftSpeakers, rightSpeakers = splitSpeakersBySide(allSpeakers)

local isStereo = #leftSpeakers > 0 and #rightSpeakers > 0
if not isStereo then
    leftSpeakers = {}
    for _, speaker in ipairs(allSpeakers) do
        leftSpeakers[#leftSpeakers + 1] = speaker
    end
    rightSpeakers = {}
end

local monitor = peripheral.find("monitor")
local chatBox = peripheral.find("chatBox")
local chatSearchResults, waitingForSelection = {}, false
local nativeTerm = term.current()
local useMonitor = false

if monitor then
    if not monitor.isColor() then
        print("Monitor found but not Advanced. Using terminal.")
    else
        monitor.setTextScale(0.5)
        -- term.redirect(monitor) -- Removed global redirect
        useMonitor = true
        nativeTerm.clear()
        nativeTerm.setCursorPos(1, 1)
        nativeTerm.write("CC Music Search Active")
    end
end

local theme = {
    bg = colors.black,
    fg = colors.white,
    accent = colors.purple,
    accent2 = colors.magenta,
    dim = colors.gray,
    dimmer = colors.lightGray,
    bar_bg = colors.gray,
    bar_fill = colors.purple,
    bar_knob = colors.white,
    ctrl = colors.lightGray,
    ctrl_hi = colors.white,
    title = colors.white,
    artist = colors.lightGray,
    lyric_cur = colors.white,
    lyric_dim = colors.gray,
    lyric_up = colors.lightGray,
    border = colors.gray,
    highlight = colors.yellow,
    queue_bg = colors.gray,
    queue_current = colors.lime,
}

local W, H = term.getSize()
local state = {
    song = nil,
    duration = 0,
    lyrics = {},
    artwork = {},
    playing = false,
    paused = false,
    quit = false,
    audioEOF = false,
    bytesSent = 0,
    audioOffset = 0,
    startTime = 0,
    pausedAt = 0,
    pauseStartTime = 0,
    seeking = false,
    lastLyricIdx = -1,
    lastElapsedStr = "",
    lastDurationStr = "",
    lastStatusText = "",
    lastDrawnLyrics = {},
    needsFullRedraw = true,
    lastUIUpdate = 0,
    lastSecond = -1,
    -- Queue support
    queue = {},
    queueIndex = 1,
    -- Double-tap back button: last tap time (ms) for go-back-a-song
    lastBackTapTime = 0,
    backLockUntil = 0,

    -- When true, playbackRunner must not advance queue (we are going back a song)
    goBackRequested = false,
    isSearching = false,
    isProcessing = false,
}

-- ===================== TIMING ========================
local function getPlaybackTime()
    if not state.playing then
        return 0
    end
    if state.paused then
        return state.pausedAt
    end
    local now = os.epoch("utc")
    return (now - state.startTime) / 1000
end

local function seekTo(targetTime)
    targetTime = math.max(0, math.min(targetTime, state.duration))
    for _, s in ipairs(allSpeakers) do
        s.stop()
    end
    local now = os.epoch("utc")
    state.startTime = now - (targetTime * 1000)
    state.audioOffset = math.floor(targetTime * 48000 / 8)
    state.bytesSent = state.audioOffset
    state.audioEOF = false
    state.seeking = true
    os.queueEvent("seek_complete")
end

-- ===================== HELPERS ==============================
local function httpGet(url, binary)
    local resp, err = http.get(url, nil, binary)
    if not resp then return nil, err end
    local body = resp.readAll()
    resp.close()
    return body
end

local function httpPost(url, data)
    local resp, err = http.post(
        url,
        textutils.serialiseJSON(data),
        { ["Content-Type"] = "application/json" }
    )
    if not resp then return nil, err end
    local body = resp.readAll()
    resp.close()
    return body
end

local function centerText(y, text, fg, bg)
    local w, h = term.getSize()
    fg = fg or theme.fg
    bg = bg or theme.bg
    local x = math.max(1, math.floor((w - #text) / 2) + 1)
    term.setCursorPos(x, y)
    term.setTextColor(fg)
    term.setBackgroundColor(bg)
    term.write(text)
end

local function fillLine(y, color)
    local w, h = term.getSize()
    term.setCursorPos(1, y)
    term.setBackgroundColor(color)
    term.write(string.rep(" ", w))
end

local function truncate(s, maxLen)
    if not s then return "" end
    if #s <= maxLen then return s end
    return s:sub(1, maxLen - 3) .. "..."
end

local function formatTime(sec)
    sec = math.max(0, math.floor(sec or 0))
    return string.format("%d:%02d", math.floor(sec / 60), sec % 60)
end

local function getLeftPaneEnd()
    local w, h = term.getSize()
    local remaining = #state.queue - state.queueIndex
    if remaining > 0 and w >= 50 then
        local queueX = w - 24
        if queueX >= 35 then
            return queueX - 2
        end
    end
    return w
end

local function playToAll(pcmL, pcmR)
    local leftToPlay = {}
    local rightToPlay = {}
    
    for i = 1, #leftSpeakers do leftToPlay[i] = true end
    for i = 1, #rightSpeakers do rightToPlay[i] = true end
    
    while true do
        local allDone = true
        for i, speaker in ipairs(leftSpeakers) do
            if leftToPlay[i] then
                if speaker.playAudio(pcmL) then
                    leftToPlay[i] = false
                else
                    allDone = false
                end
            end
        end
        
        for i, speaker in ipairs(rightSpeakers) do
            if rightToPlay[i] then
                if speaker.playAudio(pcmR) then
                    rightToPlay[i] = false
                else
                    allDone = false
                end
            end
        end
        
        if allDone then break end

        local pendingNames = {}
        local hasUnnamedPending = false
        for i, speaker in ipairs(leftSpeakers) do
            if leftToPlay[i] then
                local name = getSpeakerName(speaker)
                if #name > 0 then
                    pendingNames[name] = true
                else
                    hasUnnamedPending = true
                end
            end
        end
        for i, speaker in ipairs(rightSpeakers) do
            if rightToPlay[i] then
                local name = getSpeakerName(speaker)
                if #name > 0 then
                    pendingNames[name] = true
                else
                    hasUnnamedPending = true
                end
            end
        end

        local retryTimer = os.startTimer(SPEAKER_RETRY_TIMEOUT_S)
        while true do
            local ev, p1 = os.pullEvent()
            if ev == "seek_complete" or state.paused or state.quit or not state.playing then
                return false
            end

            if ev == "speaker_audio_empty" then
                if hasUnnamedPending or (type(p1) == "string" and pendingNames[p1]) then
                    break
                end
            elseif ev == "timer" and p1 == retryTimer then
                break
            end
        end
    end
    return true
end

local function parseDuration(durationStr)
    -- Parse duration string like "3:45" to seconds
    if type(durationStr) == "number" then
        return durationStr
    end
    if not durationStr or durationStr == "Unknown" then
        return 0
    end
    local parts = {}
    for part in durationStr:gmatch("%d+") do
        table.insert(parts, tonumber(part))
    end
    if #parts == 2 then
        return parts[1] * 60 + parts[2]
    elseif #parts == 1 then
        return parts[1]
    end
    return 0
end

local function hexToBytes(hexData)
    if type(hexData) ~= "string" or #hexData == 0 then
        return nil
    end

    local out = {}
    for i = 1, #hexData, 2 do
        out[#out + 1] = string.char(tonumber(hexData:sub(i, i + 1), 16) or 0)
    end
    return table.concat(out)
end

local function getTimestampedLyrics(lyrics)
    if type(lyrics) ~= "table" then
        return {}
    end

    local filtered = {}
    for _, line in ipairs(lyrics) do
        if type(line) == "table" then
            local ts = tonumber(line.time)
            local text = type(line.text) == "string" and line.text or nil
            if ts and ts >= 0 and text and #text > 0 then
                filtered[#filtered + 1] = { time = ts, text = text }
            end
        end
    end

    table.sort(filtered, function(a, b) return a.time < b.time end)
    return filtered
end

local function isDirectInput(input)
    input = input:lower()
    if input:match("youtube%.com") or input:match("youtu%.be") then
        return true
    end
    if #input == 11 and input:match("^[%w%-_]+$") then
        return true
    end
    return false
end

local function drawLoading(msg)
    local oldTerm = term.current()
    if useMonitor and monitor then
        term.redirect(monitor)
    end

    local w, h = term.getSize()
    local leftPaneEnd = getLeftPaneEnd()
    
    -- Clear only the left pane (the processing area)
    -- This keeps the queue visible if it was already drawn
    for y = 1, h do
        term.setCursorPos(1, y)
        term.setBackgroundColor(theme.bg)
        term.write(string.rep(" ", leftPaneEnd))
    end

    local midY = math.floor(h / 2)
    local midX = math.floor(leftPaneEnd / 2)
    
    -- Center processing text within the left pane
    local titleStr = "  Processing  "
    local msgStr = msg or "Loading..."
    
    term.setCursorPos(math.max(1, midX - math.floor(#titleStr/2)), midY - 1)
    term.setTextColor(theme.accent2)
    term.write(titleStr)
    
    term.setCursorPos(math.max(1, midX - math.floor(#msgStr/2)), midY + 1)
    term.setTextColor(theme.dimmer)
    term.write(msgStr)

    if useMonitor and monitor then
        term.redirect(oldTerm)
    end
end

-- ===================== SEARCH UI ================================
local function drawSearchScreen()
    local w, h = term.getSize()
    term.setBackgroundColor(theme.bg)
    term.clear()
    term.setCursorPos(2, 1)
    term.setTextColor(theme.accent2)
    term.write("♪ CC MUSIC SEARCH")

    local barW = w - 4
    local barX = 3
    local barY = 3

    term.setCursorPos(barX, barY)
    term.setTextColor(theme.dimmer)
    term.write("Search YouTube Music or enter video ID:")

    local inputY = barY + 1
    term.setCursorPos(barX, inputY)
    term.setBackgroundColor(theme.bar_bg)
    term.write(string.rep(" ", barW))

    centerText(h, "[Enter] Search/Play [Q] Quit", theme.dim)

    term.setCursorPos(barX + 1, inputY)
    term.setBackgroundColor(theme.bar_bg)
    term.setTextColor(colors.white)
    term.setCursorBlink(true)

    return inputY, barX, barW
end

local function drawSearchResults(results, selectedIdx, scrollOffset)
    local w, h = term.getSize()
    local resultsStartY = 6
    local resultsEndY = h - 2
    local visibleLines = resultsEndY - resultsStartY + 1

    for y = resultsStartY, resultsEndY do
        fillLine(y, theme.bg)
    end

    if #results == 0 then
        centerText(math.floor((resultsStartY + resultsEndY) / 2), "No results found", theme.dim)
        return
    end

    for i = 1, visibleLines do
        local resultIdx = scrollOffset + i
        if resultIdx > #results then break end

        local result = results[resultIdx]
        local y = resultsStartY + i - 1
        local isSelected = (resultIdx == selectedIdx)

        term.setCursorPos(2, y)
        if isSelected then
            term.setBackgroundColor(theme.accent)
            term.setTextColor(colors.black)
            term.write(">")
        else
            term.setBackgroundColor(theme.bg)
            term.setTextColor(theme.dim)
            term.write(" ")
        end

        term.setCursorPos(4, y)
        if isSelected then
            term.setBackgroundColor(theme.accent)
            term.setTextColor(colors.black)
        else
            term.setBackgroundColor(theme.bg)
            term.setTextColor(theme.fg)
        end

        -- Display: "Title - Artist"
        local artist = result.artist or "Unknown Artist"
        local titleText = truncate(result.title, w - 30) .. " - " .. truncate(artist, 15)
        term.write(titleText)

        -- Duration on the right
        local duration = result.duration or "?"
        term.setCursorPos(w - 6, y)
        if isSelected then
            term.setTextColor(colors.black)
        else
            term.setTextColor(theme.dimmer)
        end
        term.write(duration)
    end

    if #results > visibleLines then
        term.setCursorPos(w, resultsStartY)
        term.setBackgroundColor(theme.bg)
        term.setTextColor(theme.dim)
        term.write("^")
        term.setCursorPos(w, resultsEndY)
        term.write("v")
    end
end

local function selectFromResults(results)
    local selectedIdx = 1
    local scrollOffset = 0
    local w, h = term.getSize()
    local visibleLines = h - 8

    while true do
        term.setBackgroundColor(theme.bg)
                fillLine(1, theme.bg)
        term.setCursorPos(2, 1)
        term.setTextColor(theme.accent2)
        term.write("♪ SEARCH RESULTS")

        centerText(h, "[Up/Down] Navigate [Enter] Play [Backspace] Back", theme.dim)
        drawSearchResults(results, selectedIdx, scrollOffset)

        local event, key = os.pullEvent("key")
        if key == keys.up then
            selectedIdx = math.max(1, selectedIdx - 1)
            if selectedIdx < scrollOffset + 1 then
                scrollOffset = math.max(0, scrollOffset - 1)
            end
        elseif key == keys.down then
            selectedIdx = math.min(#results, selectedIdx + 1)
            if selectedIdx > scrollOffset + visibleLines then
                scrollOffset = math.min(#results - visibleLines, scrollOffset + 1)
            end
        elseif key == keys.enter then
            return results[selectedIdx]
        elseif key == keys.backspace then
            return nil
        end
    end
end

local function getSearchInput()
    state.isSearching = true
    if useMonitor then
        local oldTerm = term.current()
        term.redirect(monitor)
        term.setBackgroundColor(theme.bg)
                local w, h = term.getSize()
        centerText(math.floor(h/2) - 1, "INPUT REQUIRED", theme.accent2)
        centerText(math.floor(h/2) + 1, "Enter search on terminal", theme.dim)
        term.redirect(oldTerm)
    end

    while true do
        local inputY, barX, barW = drawSearchScreen()
        term.setCursorPos(barX + 1, inputY)
        term.setBackgroundColor(theme.bar_bg)
        term.setTextColor(colors.white)
        term.setCursorBlink(true)

        local input = read()
        term.setCursorBlink(false)

        if input == "q" or input == "Q" or input == "" then
            state.isSearching = false
            state.quit = (input == "q" or input == "Q")
            return nil
        end

        -- Check if direct video ID
        if isDirectInput(input) then
            state.isSearching = false
            return {id = input, title = input}
        else
            -- It's a search query
            drawLoading("Searching YouTube Music...")
            local body = httpPost(SERVER .. "/api/search", { query = input, maxResults = 10 })

            if not body then
                drawLoading("Search failed!")
                sleep(2)
            else
                local data = textutils.unserialiseJSON(body)
                if data and data.results and #data.results > 0 then
                    local selected = selectFromResults(data.results)
                    if selected then
                        state.isSearching = false
                        return selected
                    end
                else
                    drawLoading("No results found!")
                    sleep(2)
                end
            end
        end
    end
end

-- ===================== PROCESS SONG =========================
local function processSong(videoId)
    state.isProcessing = true
    drawLoading("Processing: " .. videoId)

    local body, err = httpPost(SERVER .. "/api/process", { url = videoId })
    if not body then
        drawLoading("Error: " .. tostring(err))
        sleep(3)
        return false
    end

    local data = textutils.unserialiseJSON(body)
    if not data or data.error then
        drawLoading("Error: " .. (data and data.error or "Unknown"))
        sleep(3)
        return false
    end

    state.song = data
    state.duration = data.duration or 0

    state.lyrics = {}
    if data.hasLyrics then
        local lBody = httpGet(SERVER .. "/api/lyrics/" .. data.id)
        if lBody then
            state.lyrics = getTimestampedLyrics(textutils.unserialiseJSON(lBody))
        end
    end

    local aBody = httpGet(SERVER .. "/api/artwork/" .. data.id)
    if aBody then
        state.artwork = {}
        for line in aBody:gmatch("[^\n]+") do
            local parts = {}
            for part in line:gmatch("[^|]+") do
                table.insert(parts, part)
            end
            if #parts == 3 then
                state.artwork[#state.artwork + 1] = {
                    text = parts[1],
                    fg = parts[2],
                    bg = parts[3]
                }
            end
        end
    else
        state.artwork = {}
    end

    state.playing = true
    state.paused = false
    state.audioEOF = false
    state.audioOffset = 0
    state.bytesSent = 0
    state.seeking = true
    state.startTime = os.epoch("utc")
    state.pausedAt = 0
    state.isProcessing = false

    return true
end

-- ===================== UI DRAWING ===========================
local function drawArtwork(startX, startY)
    if #state.artwork == 0 then return end
    for y, line in ipairs(state.artwork) do
        term.setCursorPos(startX, startY + y - 1)
        term.blit(line.text, line.fg, line.bg)
    end
end

local function drawQueue(panelTop)
local w, h = term.getSize()
local remaining = #state.queue - state.queueIndex

-- NO QUEUE = NOTHING on right side at all
if remaining <= 0 then return end

local queueX = w - 24


if remaining <= 0 then 
    local queueWidth = w - queueX + 1
    if queueX > 0 and queueX <= w then
        for y = 1, h do
            term.setCursorPos(queueX - 1, y)
            term.setBackgroundColor(theme.bg)
            term.write(string.rep(" ", queueWidth + 1))
        end
    end
    return 
end

if queueX < 30 then return end  -- Reduced threshold

-- Explicitly define queueWidth before use
local queueWidth = w - queueX + 1

-- Draw clean visual divider at queueX - 1
for y = 1, h do
    term.setCursorPos(queueX - 1, y)
    term.setBackgroundColor(theme.bg)
    term.setTextColor(theme.accent)
    term.write("|")
end

-- Clear and draw queue header
term.setCursorPos(queueX, 1)
term.setBackgroundColor(theme.bg)
term.write(string.rep(" ", queueWidth - 1))
term.setCursorPos(queueX, 1)
term.setTextColor(theme.accent)
term.write("QUEUE")

-- Show remaining count
term.setCursorPos(queueX, 2)
term.setBackgroundColor(theme.bg)
term.write(string.rep(" ", queueWidth - 1))
term.setCursorPos(queueX, 2)
term.setTextColor(theme.highlight)
local remaining = #state.queue - state.queueIndex
term.write(remaining .. " left")

-- Separator line
term.setCursorPos(queueX, 3)
term.setTextColor(theme.dim)
local sepWidth = math.min(queueWidth - 1, 23)
term.write(string.rep("-", sepWidth))

-- Draw queue items (starting from current + 1)
-- Fill as much vertical space as available
local y = 4
for i = state.queueIndex + 1, #state.queue do
    if y >= h - 1 then break end  -- Stop before bottom of screen

    local video = state.queue[i]
    local num = i - state.queueIndex

    -- Clear the line first
    term.setCursorPos(queueX, y)
    term.setBackgroundColor(theme.bg)
    term.write(string.rep(" ", queueWidth - 1))

    term.setCursorPos(queueX, y)
    term.setBackgroundColor(theme.bg)
    term.setTextColor(theme.accent)
    term.write(num .. ".")

    term.setCursorPos(queueX + 3, y)
    term.setTextColor(theme.fg)
    local title = video.title or video.id or "Unknown"
    local maxWidth = queueWidth - 4  -- Account for "1. " prefix
    if maxWidth > 0 then
        title = truncate(title, maxWidth)
        term.write(title)
    end

    y = y + 1
end

-- Show "Empty" if no upcoming songs
if #state.queue - state.queueIndex == 0 then
    -- Clear previous items below header if queue just became empty
    for i = y, h - 1 do
        term.setCursorPos(queueX, i)
        term.setBackgroundColor(theme.bg)
        term.write(string.rep(" ", queueWidth - 1))
    end
    term.setCursorPos(queueX, 4)
    term.setBackgroundColor(theme.bg)
    term.setTextColor(theme.dim)
    term.write("Empty")
end
end


local function drawProgressBar(y, elapsed, leftPaneEnd)
    local w, h = term.getSize()
    local duration = state.duration > 0 and state.duration or 1

    local maxBarW = 80

    -- FULL width bar (no padding)
    local barLen = leftPaneEnd

    local barStart = math.max(1, math.floor((leftPaneEnd - barLen) / 2))
    local barEnd = barStart + barLen - 1

    local progress = math.min(elapsed / duration, 1.0)
    local filled = math.floor(progress * barLen)

    term.setBackgroundColor(theme.bg)
    term.setTextColor(theme.dimmer)

    local timeL = formatTime(elapsed)
    local timeR = formatTime(duration)

    -- Left timestamp
    term.setCursorPos(barStart, y + 1)
    term.write(timeL)

    -- Right timestamp (hard clamped inside bar)
    local timeRX = barEnd - #timeR + 1
    timeRX = math.max(timeRX, barStart + #timeL + 2)

    term.setCursorPos(timeRX, y + 1)
    term.write(timeR)

    local barText = ""
    local barFg = ""
    local barBg = ""

    for i = 1, barLen do
        if i == filled + 1 then
            barText = barText .. "\x07"
            barFg = barFg .. "0"
            barBg = barBg .. "f"
        elseif i <= filled then
            barText = barText .. "\x8c"
            barFg = barFg .. "a"
            barBg = barBg .. "f"
        else
            barText = barText .. "\x8c"
            barFg = barFg .. "7"
            barBg = barBg .. "f"
        end
    end

    term.setCursorPos(barStart, y)
    term.blit(barText, barFg, barBg)

    return barStart, barEnd, y
end


local function drawControls(y, leftPaneEnd)
    -- Clear controls line up to leftPaneEnd
    term.setCursorPos(1, y)
    term.setBackgroundColor(theme.bg)
    term.write(string.rep(" ", leftPaneEnd))
    
    local prev = "\x11\x11"
    local play = state.paused and " \x10 " or "\x7c\x7c"
    local skip = "\x10\x10"
    local ctrl = "  " .. prev .. "   " .. play .. "   " .. skip .. "  "
    
    -- Center within left pane
    local x = math.max(1, math.floor((leftPaneEnd - #ctrl) / 2) + 1)
    term.setCursorPos(x, y)
    term.setTextColor(theme.ctrl_hi)
    term.setBackgroundColor(theme.bg)
    term.write(ctrl)
    
    -- Store control positions for touch detection
    state.controlsY = y
    state.controlsX = x
    state.controlsWidth = #ctrl
    state.leftPaneEnd = leftPaneEnd
end

local function drawNowPlaying(elapsed)
    if not state.song then return end
    local song = state.song
    local w, h = term.getSize()

    local leftPaneEnd = getLeftPaneEnd()

    local artH = #state.artwork
    local artW = artH > 0 and #state.artwork[1].text or 0
    local panelH = math.max(artH, 4) + 4
    local panelTop = h - panelH + 1

    -- Separator
    term.setCursorPos(1, panelTop)
    term.setBackgroundColor(theme.bg)
    term.setTextColor(theme.border)
    term.write(string.rep("\x8c", leftPaneEnd))

    local contentTop = panelTop + 1

    -- 🔒 HARD LEFT ANCHOR
    local artX = 2

    if artH > 0 then
        drawArtwork(artX, contentTop)
    end

    local infoX = artH > 0 and (artX + artW + 2) or artX
    local infoW = leftPaneEnd - infoX - 2

    term.setCursorPos(infoX, contentTop)
    term.setBackgroundColor(theme.bg)
    term.setTextColor(theme.title)
    term.write(truncate(song.title or "Unknown", infoW))

    term.setCursorPos(infoX, contentTop + 1)
    term.setTextColor(theme.artist)
    term.write(truncate(song.artist or "Unknown Artist", infoW))

    if song.album and #song.album > 0 then
        term.setCursorPos(infoX, contentTop + 2)
        term.setTextColor(theme.dim)
        term.write(truncate(song.album, infoW))
    end

    local spkY = contentTop + 3
    if spkY < h - 3 then
        term.setCursorPos(infoX, spkY)
        term.setTextColor(theme.accent)
        term.write("\x0e ")
        term.setTextColor(theme.dim)

        local spkText = isStereo
            and ("Stereo (" .. #leftSpeakers .. "L / " .. #rightSpeakers .. "R)")
            or ("Mono (" .. #allSpeakers .. " spk)")

        term.write(truncate(spkText, infoW - 2))
    end

    local barStart, barEnd, barY = drawProgressBar(h - 2, elapsed, leftPaneEnd)
    drawControls(h, leftPaneEnd)

    return panelTop, barStart, barEnd, barY
end


local function drawLyrics(panelTop, currentTime)
    if not state.song then return end
    local w, h = term.getSize()

    -- Calculate leftPaneEnd dynamically based on queue visibility
    local leftPaneEnd = getLeftPaneEnd()

    -- Adjust for queue on the right
    local lyricsStart = 2
    local lyricsEnd = (panelTop or h) - 1
    local lyricsH = lyricsEnd - lyricsStart + 1
    local lyricsW = leftPaneEnd - 2

    if lyricsH < 3 then return end

    -- Clear lyrics area up to leftPaneEnd
    for y = lyricsStart, lyricsEnd do
        term.setCursorPos(1, y)
        term.setBackgroundColor(theme.bg)
        term.write(string.rep(" ", leftPaneEnd - 1))
    end

    if #state.lyrics == 0 then
        local mid = math.floor((lyricsStart + lyricsEnd) / 2)
        centerText(mid, "\x07 No lyrics available \x07", theme.dim)
        return
    end

    local currentIdx = 1
    for i = 1, #state.lyrics do
        if state.lyrics[i].time <= currentTime then
            currentIdx = i
        else
            break
        end
    end

    local centerY = math.floor((lyricsStart + lyricsEnd) / 2)
    local startIdx = currentIdx - (centerY - lyricsStart)

    for screenY = lyricsStart, lyricsEnd do
        -- Clear the line first to prevent artifacts
        term.setCursorPos(1, screenY)
        term.setBackgroundColor(theme.bg)
        term.write(string.rep(" ", leftPaneEnd - 1))
        
        local lyricIdx = startIdx + (screenY - lyricsStart)
        if lyricIdx >= 1 and lyricIdx <= #state.lyrics then
            local text = state.lyrics[lyricIdx].text or ""
            local color

            if lyricIdx == currentIdx then
                color = theme.lyric_cur
            elseif lyricIdx < currentIdx then
                color = theme.lyric_dim
            else
                color = theme.lyric_up
            end

            -- Ensure text fits within available width
            text = truncate(text, lyricsW - 2)  -- Extra margin for safety

            -- Center within available lyrics space
            local lyricX = math.max(2, math.floor((leftPaneEnd - #text) / 2) + 1)
            if lyricX + #text - 1 <= leftPaneEnd - 1 then
                term.setCursorPos(lyricX, screenY)
                term.setBackgroundColor(theme.bg)
                term.setTextColor(color)
                term.write(text)

                if lyricIdx == currentIdx and lyricX > 2 then
                    term.setCursorPos(lyricX - 2, screenY)
                    term.setTextColor(theme.accent)
                    term.write("\x10")
                end
            end
        end
    end
end

local function drawUI()
    if not useMonitor or not monitor or state.isProcessing then return end
    
    local oldTerm = term.current()
    term.redirect(monitor)
    
    local w, h = term.getSize()
    term.setBackgroundColor(theme.bg)
    
    -- Calculate leftPaneEnd dynamically based on queue visibility
    local leftPaneEnd = getLeftPaneEnd()

    -- Clear header line up to leftPaneEnd
    term.setCursorPos(1, 1)
    term.setBackgroundColor(theme.bg)
    term.write(string.rep(" ", leftPaneEnd - 1))
    
    term.setCursorPos(2, 1)
    term.setTextColor(theme.accent2)
    term.setBackgroundColor(theme.bg)
    term.write("\x0e CC Music")

    local statusText = ""
    if state.playing then
        statusText = state.paused and "PAUSED" or "PLAYING"
    end
    if #statusText > 0 then
        local statusX = math.min(leftPaneEnd - #statusText - 1, w - #statusText)
        if statusX >= 2 and statusX + #statusText - 1 <= leftPaneEnd - 1 then
            term.setCursorPos(statusX, 1)
            term.setTextColor(state.paused and theme.dim or theme.accent)
            term.write(statusText)
        end
    end

    local elapsed = getPlaybackTime()
    local lyricTime = elapsed + LYRIC_OFFSET

    local panelTop, barStart, barEnd, barY = drawNowPlaying(elapsed)
    drawQueue(panelTop)
    drawLyrics(panelTop, lyricTime)

    state.barStart = barStart
    state.barEnd = barEnd
    state.barY = barY
    
    term.redirect(oldTerm)
end

-- ===================== AUDIO ENGINE =========================
local function audioThread()
    local decoderL = dfpwm.make_decoder()
    local decoderR = dfpwm.make_decoder()
    local CHUNK_SIZE = AUDIO_CHUNK_SIZE

    while state.playing and not state.quit do
        while state.paused and not state.quit do
            os.pullEvent("resume_audio")
        end

        if state.quit then break end

        if state.seeking then
            decoderL = dfpwm.make_decoder()
            decoderR = dfpwm.make_decoder()
            state.seeking = false
        end

        if state.audioEOF then
            sleep(2)
            state.playing = false
            break
        end

        local done = false
        local rawL, rawR

        if isStereo then
            local bodyL = httpGet(SERVER .. "/api/audio/" .. state.song.id .. "/chunk?channel=left&offset=" .. state.audioOffset .. "&size=" .. CHUNK_SIZE)
            local bodyR = httpGet(SERVER .. "/api/audio/" .. state.song.id .. "/chunk?channel=right&offset=" .. state.audioOffset .. "&size=" .. CHUNK_SIZE)

            if not bodyL or not bodyR then
                sleep(0.5)
            else
                local respL = textutils.unserialiseJSON(bodyL)
                local respR = textutils.unserialiseJSON(bodyR)

                if respL and respL.data and #respL.data > 0 and respR and respR.data then
                    rawL = hexToBytes(respL.data)
                    rawR = hexToBytes(respR.data)
                    if respL.done then done = true end
                elseif respL and respL.done then
                    done = true
                else
                    sleep(0.5)
                end
            end
        else
            local body = httpGet(SERVER .. "/api/audio/" .. state.song.id .. "/chunk?offset=" .. state.audioOffset .. "&size=" .. CHUNK_SIZE)

            if not body then
                sleep(0.5)
            else
                local resp = textutils.unserialiseJSON(body)
                if resp and resp.data and #resp.data > 0 then
                    rawL = hexToBytes(resp.data)
                    rawR = rawL
                    if resp.done then done = true end
                elseif resp and resp.done then
                    done = true
                else
                    sleep(0.5)
                end
            end
        end

        if rawL and rawR then
            local pcmL = decoderL(rawL)
            local pcmR = isStereo and decoderR(rawR) or pcmL

            if not playToAll(pcmL, pcmR) then
                -- Break the loop if we need to (seek, pause, etc)
                if state.seeking or state.paused or state.quit or not state.playing then
                    -- nothing - loop will continue or exit naturally
                end
            end

            if not state.paused and not state.quit and not state.seeking then
                state.bytesSent = state.bytesSent + #rawL
                state.audioOffset = state.audioOffset + #rawL
                if done then state.audioEOF = true end
            end
        end
    end
end

local function uiThread()
    while state.playing and not state.quit do
        drawUI()
        sleep(0.5)
    end
end

local function inputThread()
    while not state.quit do
        local pack = { os.pullEvent() }
        local ev = pack[1]

        if state.isSearching and (ev == "key" or ev == "char") then
            -- handled by read()

        elseif ev == "key" then
            local key = pack[2]

            if key == keys.space then
                if not state.paused then
                    state.pausedAt = getPlaybackTime()
                    state.paused = true
                    for _, s in ipairs(allSpeakers) do s.stop() end
                else
                    seekTo(state.pausedAt)
                    state.paused = false
                    os.queueEvent("resume_audio")
                end

            elseif key == keys.q then
                state.quit = true
                state.playing = false
                return

            elseif key == keys.n then
                state.playing = false
                return
            end

        elseif ev == "monitor_touch" or ev == "mouse_click" then
            local x, y
            if ev == "monitor_touch" then
                x = pack[3]
                y = pack[4]
            else
                x = pack[3]
                y = pack[4]
            end

            -- Progress bar
            if state.barY and y == state.barY and x >= state.barStart and x <= state.barEnd then
                local barLen = state.barEnd - state.barStart + 1
                local clickPos = x - state.barStart
                seekTo((clickPos / barLen) * state.duration)
                state.paused = false

            else
                local w, h = term.getSize()
                local leftPaneEnd = getLeftPaneEnd()
                local controlsRow = state.controlsY or h
                local ctrlStart = state.controlsX or math.max(1, math.floor((leftPaneEnd - 16) / 2) + 1)

                if y == controlsRow and x < leftPaneEnd then
                    local relX = x - ctrlStart
                    local now = os.epoch("utc")

                    -- BACK (double tap allowed, triple blocked)
                    if relX >= 2 and relX <= 3 then
                        -- Hard lock after double tap
                        if now < (state.backLockUntil or 0) then
                            return
                        end

                        -- First song: restart only
                        if state.queueIndex <= 1 then
                            state.lastBackTapTime = 0
                            seekTo(0)
                            return
                        end

                        -- Second tap = previous
                        if state.lastBackTapTime ~= 0 and (now - state.lastBackTapTime) < BACK_DOUBLE_TAP_TIMEOUT_MS then
                            state.lastBackTapTime = 0
                            state.backLockUntil = now + 800

                            state.goBackRequested = true
                            state.playing = false
                            state.audioEOF = true
                            for _, s in ipairs(allSpeakers) do s.stop() end
                            state.queueIndex = state.queueIndex - 1
                            return
                        end

                        -- First tap = restart
                        state.lastBackTapTime = now
                        seekTo(0)

                    -- PLAY / PAUSE
                    elseif relX >= 7 and relX <= 9 then
                        if not state.paused then
                            state.pausedAt = getPlaybackTime()
                            state.paused = true
                            for _, s in ipairs(allSpeakers) do s.stop() end
                        else
                            seekTo(state.pausedAt)
                            state.paused = false
                            os.queueEvent("resume_audio")
                        end

                    -- SKIP
                    elseif relX >= 11 and relX <= 15 then
                        state.playing = false
                        state.audioEOF = true
                    end

                elseif y == h and x > leftPaneEnd - 6 and x < leftPaneEnd then
                    state.playing = false
                    state.audioEOF = true
                end
            end
        end
    end
end



local function isPlaylistId(str)
    if #str < 13 then return false end
    return str:match("^PL") or str:match("^OLA") or str:match("^RDCLAK") or str:match("^VL") or str:match("^UU") or str:match("^OLAK")
end

local function fetchPlaylist(playlistId)
    local body = httpPost(SERVER .. "/api/playlist", { playlistId = playlistId })
    if not body then return nil end
    local data = textutils.unserialiseJSON(body)
    if not data or data.error then return nil end
    return data
end

local function cacheThread()
    while state.playing and not state.quit do
        if #state.queue > state.queueIndex then
            local nextVideo = state.queue[state.queueIndex + 1]
            if not state.nextCached or state.nextCached ~= nextVideo.id then
                pcall(function()
                    local body = httpPost(SERVER .. "/api/process", { url = nextVideo.id })
                    if body then
                        local data = textutils.unserialiseJSON(body)
                        if data and not data.error then state.nextCached = nextVideo.id end
                    end
                end)
            end
        end
        sleep(2)
    end
end

local function chatSend(msg)
    if chatBox then pcall(function() chatBox.sendMessage(msg, "CC-Music") end) end
end

-- Runs playback in its own thread so chat can keep processing .pause, .queue, etc.
local function playbackRunner()
    while not state.quit do
        if state.playing then
            parallel.waitForAny(audioThread, uiThread, inputThread, cacheThread)
            for _, s in ipairs(allSpeakers) do s.stop() end
            if state.quit then
                -- nothing
            elseif state.goBackRequested then
                state.goBackRequested = false
                -- Load previous song here so we can restart threads immediately (avoids stuck "Processing" screen)
                if state.queueIndex >= 1 and state.queueIndex <= #state.queue then
                    local video = state.queue[state.queueIndex]
                    if video then
                        processSong(video.id)
                    end
                end
            elseif not state.playing then
                -- Song ended or was skipped
                state.queueIndex = state.queueIndex + 1
                if state.queueIndex <= #state.queue then
                    local video = state.queue[state.queueIndex]
                    if processSong(video.id) then
                        state.audioEOF = false
                        if chatBox then chatSend("| " .. (video.title or video.id or "Next")) end
                        sleep(0.5)
                    end
                else
                    if chatBox then chatSend("| Done!") end
                    state.playing = false
                    state.paused = false
                    state.audioEOF = false
                end
            end
        else
            -- Short sleep so we react quickly when state.playing becomes true (e.g. after go-back or chat .play)
            sleep(0.1)
        end
    end
end

local function chatThread()
    if chatBox then
        sleep(1)
        chatSend("| CC Music online! Commands: .play <query/videoID/playlistID>, .pause, .resume, .next, .queue")
    end

    while not state.quit do
        local ok, event, username, message = pcall(function() return os.pullEvent("chat") end)
        if ok and event == "chat" and message then
        if message:sub(1, 1) == "." then
            local cmd = message:match("^%.(%w+)")
            local args = message:match("^%.%w+%s+(.+)")

            if cmd == "play" and args then
                pcall(function()
                    if isPlaylistId(args) then
                        chatSend("| Loading...")
                        local pl = fetchPlaylist(args)
                        if pl and pl.tracks and #pl.tracks > 0 then
                            chatSend("| " .. (pl.title or "Playlist") .. " (" .. #pl.tracks .. " songs)")
                            if state.playing then state.audioEOF = true state.playing = false
                                for _, s in ipairs(allSpeakers) do s.stop() end sleep(0.5) end
                            state.queue = pl.tracks
                            state.queueIndex = 1
                            state.nextCached = nil
                            if processSong(pl.tracks[1].id) then
                                chatSend("| " .. (pl.tracks[1].title or "Playing"))
                            end
                            -- playbackRunner thread handles the rest; chat stays responsive
                        else chatSend("| Not found") end
                    elseif #args == 11 and args:match("^[%w_-]+$") then
                        chatSend("| Playing...")
                        if state.playing then
                            state.audioEOF = true
                            state.playing = false
                            for _, s in ipairs(allSpeakers) do s.stop() end
                            sleep(1)
                        end
                        state.queue = {{id = args, title = "Video " .. args}}
                        state.queueIndex = 1
                        state.nextCached = nil
                        state.playing = false
                        state.paused = false
                        state.audioEOF = false
                        processSong(args)
                        -- playbackRunner handles waitForAny; chat stays responsive
                    else
                        chatSend("| Searching...")
                        local body = httpPost(SERVER .. "/api/search", { query = args, maxResults = 5 })
                        if body then
                            local data = textutils.unserialiseJSON(body)
                            if data and data.results and #data.results > 0 then
                                chatSearchResults = {}
                                for i = 1, math.min(5, #data.results) do chatSearchResults[i] = data.results[i] end
                                waitingForSelection = true
                                chatSend("| Top 5:")
                                sleep(1)
                                for i = 1, #chatSearchResults do
                                    chatSend(i .. ". " .. chatSearchResults[i].title)
                                    sleep(1)
                                end
                                chatSend("Reply 1-5")
                            else chatSend("| No results") end
                        end
                    end
                end)
            elseif cmd == "pause" and state.playing and not state.paused then
                state.pausedAt = getPlaybackTime()
                state.paused = true
                for _, s in ipairs(allSpeakers) do s.stop() end
                chatSend("| Paused")
            elseif cmd == "resume" and state.playing and state.paused then
                seekTo(state.pausedAt)
                state.paused = false
                os.queueEvent("resume_audio")
                chatSend("| Resumed")
            elseif cmd == "back" then
                if #state.queue > 0 and state.queueIndex > 1 then
                    chatSend("| Going back...")
                    state.goBackRequested = true
                    state.playing = false
                    state.audioEOF = true
                    for _, s in ipairs(allSpeakers) do s.stop() end
                    state.queueIndex = state.queueIndex - 1
                else
                    chatSend("| Can't go back")
                end
            elseif cmd == "next" and #state.queue > 0 then
                state.audioEOF = true
                state.playing = false
                chatSend("| Skipping")
            elseif cmd == "queue" and #state.queue > 0 then
                local remaining = #state.queue - state.queueIndex
                if remaining == 0 then chatSend("| Last song")
                else
                    chatSend("| Next " .. math.min(5, remaining) .. ":")
                    sleep(1)
                    for i = state.queueIndex + 1, math.min(state.queueIndex + 5, #state.queue) do
                        local v = state.queue[i]
                        chatSend((i - state.queueIndex) .. ". " .. (v.title or v.id))
                        sleep(1)
                    end
                end
            elseif cmd == "clear" then
                state.queue = {}
                state.queueIndex = 1
                state.nextCached = nil
                chatSend("| Queue cleared")
            end
        elseif waitingForSelection then
            local sel = tonumber(message)
            if sel and sel >= 1 and sel <= #chatSearchResults then
                local result = chatSearchResults[sel]
                waitingForSelection = false
                chatSearchResults = {}
                chatSend("| " .. result.title)
                if state.playing then state.audioEOF = true state.playing = false
                    for _, s in ipairs(allSpeakers) do s.stop() end sleep(0.5) end
                state.queue = {result}
                state.queueIndex = 1
                state.nextCached = nil
                state.playing = false
                state.paused = false
                state.audioEOF = false
                processSong(result.id)
                -- playbackRunner handles waitForAny; chat stays responsive
            end
        end
        else
            -- Error or non-chat event - brief pause and continue loop
            sleep(0.1)
        end
    end
end

-- ===================== MAIN =================================
local function main()

    -- HARD clear on program start (terminal + monitor)
    term.setBackgroundColor(theme.bg)
    term.clear()
    term.setCursorPos(1,1)

    if useMonitor and monitor then
        local old = term.current()
        term.redirect(monitor)
        term.setBackgroundColor(theme.bg)
        term.clear()
        term.setCursorPos(1,1)
        term.redirect(old)
    end

    while not state.quit do
        local input = getSearchInput()
        if state.quit then break end

        if input then
            -- Immediate switch behavior
            if state.playing then
                state.playing = false
                state.audioEOF = true
                for _, s in ipairs(allSpeakers) do s.stop() end
                sleep(0.2)
            end

            -- Reset queue to new single-item search result
            state.queue = {input}
            state.queueIndex = 1
            state.nextCached = nil
            
            -- Start playback
            processSong(input.id)
        end
    end

    term.setBackgroundColor(colors.black)
    term.setTextColor(colors.white)
    term.setCursorPos(1,1)
    print("Thanks for listening!")
end



parallel.waitForAny(chatThread, main, playbackRunner)
