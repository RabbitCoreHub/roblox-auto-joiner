local API_URL = "https://d14b0190-6f03-4e17-891a-c03cea8e1d19-00-3cfj2zt8ev9zl.spock.replit.dev"
local POLL_INTERVAL = 2
local JOIN_TIMEOUT = 5

local HttpService = game:GetService("HttpService")
local TeleportService = game:GetService("TeleportService")
local Players = game:GetService("Players")

local isJoining = false
local autoJoinEnabled = true
local lastJobId = nil
local isRunning = true
local playerUsername = Players.LocalPlayer.Name

local gui = nil
local mainFrame = nil
local statusLabel = nil
local nameLabel = nil
local moneyLabel = nil
local playersLabel = nil
local autoJoinButton = nil

local ACCENT_COLOR = Color3.fromRGB(88, 101, 242)
local BG_COLOR = Color3.fromRGB(32, 34, 37)
local SECONDARY_BG = Color3.fromRGB(47, 49, 54)
local TEXT_COLOR = Color3.fromRGB(255, 255, 255)
local SUCCESS_COLOR = Color3.fromRGB(87, 242, 135)
local ERROR_COLOR = Color3.fromRGB(237, 66, 69)
local WARNING_COLOR = Color3.fromRGB(254, 231, 92)

local function httpRequest(url, method, body)
    local success, response = pcall(function()
        if request then
            local httpResponse = request({
                Url = url,
                Method = method or "GET",
                Headers = {["Content-Type"] = "application/json"},
                Body = body and HttpService:JSONEncode(body) or nil
            })
            if httpResponse.StatusCode == 200 or httpResponse.StatusCode == "200" then
                return httpResponse.Body
            else
                print("[HTTP ERROR] Status Code: " .. tostring(httpResponse.StatusCode))
                print("[HTTP ERROR] URL: " .. url)
                error("HTTP Error: " .. tostring(httpResponse.StatusCode))
            end
        else
            if method == "POST" then
                return HttpService:PostAsync(url, HttpService:JSONEncode(body), Enum.HttpContentType.ApplicationJson)
            else
                return HttpService:GetAsync(url)
            end
        end
    end)

    if success and response then
        local parseSuccess, data = pcall(function()
            return HttpService:JSONDecode(response)
        end)
        if parseSuccess and data then
            return data
        else
            print("[JSON ERROR] Failed to parse response")
            print("[JSON ERROR] Response: " .. tostring(response))
        end
    else
        print("[REQUEST ERROR] " .. tostring(response))
    end

    return nil
end

local function log(message, color)
    print("[" .. os.date("%H:%M:%S") .. "] " .. message)
    if statusLabel then
        statusLabel.Text = message
        statusLabel.TextColor3 = color or TEXT_COLOR
    end
end

local function tweenSize(object, endSize, duration)
    local TweenService = game:GetService("TweenService")
    local tween = TweenService:Create(
        object,
        TweenInfo.new(duration or 0.3, Enum.EasingStyle.Quint, Enum.EasingDirection.Out),
        {Size = endSize}
    )
    tween:Play()
end

local function tweenBackgroundColor(object, endColor, duration)
    local TweenService = game:GetService("TweenService")
    local tween = TweenService:Create(
        object,
        TweenInfo.new(duration or 0.2, Enum.EasingStyle.Linear),
        {BackgroundColor3 = endColor}
    )
    tween:Play()
end

local function createCorner(parent, radius)
    local corner = Instance.new("UICorner")
    corner.CornerRadius = UDim.new(0, radius or 8)
    corner.Parent = parent
    return corner
end

local function createGradient(parent)
    local gradient = Instance.new("UIGradient")
    gradient.Color = ColorSequence.new({
        ColorSequenceKeypoint.new(0, Color3.fromRGB(88, 101, 242)),
        ColorSequenceKeypoint.new(1, Color3.fromRGB(137, 87, 229))
    })
    gradient.Rotation = 45
    gradient.Parent = parent
    return gradient
end

local function makeDraggable(frame)
    local dragging = false
    local dragInput
    local dragStart
    local startPos

    local function update(input)
        local delta = input.Position - dragStart
        frame.Position = UDim2.new(startPos.X.Scale, startPos.X.Offset + delta.X, startPos.Y.Scale, startPos.Y.Offset + delta.Y)
    end

    frame.InputBegan:Connect(function(input)
        if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
            dragging = true
            dragStart = input.Position
            startPos = frame.Position

            input.Changed:Connect(function()
                if input.UserInputState == Enum.UserInputState.End then
                    dragging = false
                end
            end)
        end
    end)

    frame.InputChanged:Connect(function(input)
        if input.UserInputType == Enum.UserInputType.MouseMovement or input.UserInputType == Enum.UserInputType.Touch then
            dragInput = input
        end
    end)

    game:GetService("UserInputService").InputChanged:Connect(function(input)
        if input == dragInput and dragging then
            update(input)
        end
    end)
end

local function updateGUI(serverData)
    if not gui then return end

    if nameLabel then
        nameLabel.Text = serverData.name or "Unknown Server"
    end

    if moneyLabel then
        local moneyValue = tonumber(serverData.money) or 0
        moneyLabel.Text = string.format("%.1fM/s", moneyValue)
        
        if serverData.is_10m_plus then
            moneyLabel.TextColor3 = WARNING_COLOR
        else
            moneyLabel.TextColor3 = SUCCESS_COLOR
        end
    end

    if playersLabel then
        playersLabel.Text = serverData.players or "0/0"
    end
end

local function joinServer(serverData)
    if not autoJoinEnabled then
        log("Auto-join is disabled", WARNING_COLOR)
        return
    end

    if isJoining then
        log("Already attempting to join...", WARNING_COLOR)
        return
    end

    if not serverData.job_id or serverData.job_id == "" then
        log("No job ID available", ERROR_COLOR)
        return
    end

    if serverData.job_id == lastJobId then
        log("Skipping duplicate server", WARNING_COLOR)
        return
    end

    lastJobId = serverData.job_id
    isJoining = true
    
    log("Attempting to join: " .. (serverData.name or "Unknown"), ACCENT_COLOR)

    local teleportConnection
    teleportConnection = TeleportService.TeleportInitFailed:Connect(function(player, teleportResult, errorMessage)
        if player == Players.LocalPlayer then
            log("Teleport failed: " .. errorMessage, ERROR_COLOR)
            log("Moving to next server...", WARNING_COLOR)

            isJoining = false
            lastJobId = nil

            if teleportConnection then
                teleportConnection:Disconnect()
            end
        end
    end)

    task.spawn(function()
        local success, errorMessage = pcall(function()
            local placeId = 109983668079237
            local jobId = serverData.job_id
            
            TeleportService:TeleportToPlaceInstance(placeId, jobId, Players.LocalPlayer)
        end)

        if not success then
            log("Join failed: " .. tostring(errorMessage), ERROR_COLOR)
            log("Moving to next server...", WARNING_COLOR)

            isJoining = false
            lastJobId = nil

            if teleportConnection then
                teleportConnection:Disconnect()
            end
        else
            log("Teleport initiated...", SUCCESS_COLOR)
        end
    end)
end

local function fetchServerData()
    local data = httpRequest(API_URL .. "/api/server/pull")

    if data and data.status == "success" and data.data then
        return data.data
    end

    return nil
end

local function startPolling()
    task.spawn(function()
        log("Starting HTTP polling...", SUCCESS_COLOR)
        
        while isRunning do
            if autoJoinEnabled and not isJoining then
                local serverData = fetchServerData()
                
                if serverData and serverData.job_id and serverData.job_id ~= "" then
                    log("New server data received!", SUCCESS_COLOR)
                    updateGUI(serverData)
                    joinServer(serverData)
                end
            end
            
            task.wait(POLL_INTERVAL)
        end
    end)
end

function createMainGUI()
    gui = Instance.new("ScreenGui")
    gui.Name = "RobloxAutoJoiner"
    gui.ResetOnSpawn = false
    gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
    gui.Parent = game:GetService("CoreGui")

    mainFrame = Instance.new("Frame")
    mainFrame.Size = UDim2.new(0, 400, 0, 0)
    mainFrame.Position = UDim2.new(0.5, -200, 0.5, -140)
    mainFrame.BackgroundColor3 = BG_COLOR
    mainFrame.BorderSizePixel = 0
    mainFrame.Parent = gui
    createCorner(mainFrame, 12)
    
    makeDraggable(mainFrame)

    local header = Instance.new("Frame")
    header.Size = UDim2.new(1, 0, 0, 60)
    header.BackgroundColor3 = ACCENT_COLOR
    header.BorderSizePixel = 0
    header.Parent = mainFrame
    createCorner(header, 12)
    createGradient(header)

    local titleLabel = Instance.new("TextLabel")
    titleLabel.Size = UDim2.new(1, -20, 0, 30)
    titleLabel.Position = UDim2.new(0, 10, 0, 5)
    titleLabel.BackgroundTransparency = 1
    titleLabel.Text = "AUTO-JOINER (ACTIVE)"
    titleLabel.TextColor3 = TEXT_COLOR
    titleLabel.Font = Enum.Font.GothamBold
    titleLabel.TextSize = 20
    titleLabel.TextXAlignment = Enum.TextXAlignment.Left
    titleLabel.Parent = header

    local subtitleLabel = Instance.new("TextLabel")
    subtitleLabel.Size = UDim2.new(1, -20, 0, 20)
    subtitleLabel.Position = UDim2.new(0, 10, 0, 35)
    subtitleLabel.BackgroundTransparency = 1
    subtitleLabel.Text = "by IceHub, RabbitCore | " .. playerUsername
    subtitleLabel.TextColor3 = TEXT_COLOR
    subtitleLabel.Font = Enum.Font.Gotham
    subtitleLabel.TextSize = 12
    subtitleLabel.TextXAlignment = Enum.TextXAlignment.Left
    subtitleLabel.TextTransparency = 0.3
    subtitleLabel.Parent = header

    local closeButton = Instance.new("TextButton")
    closeButton.Size = UDim2.new(0, 40, 0, 40)
    closeButton.Position = UDim2.new(1, -50, 0, 10)
    closeButton.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
    closeButton.BackgroundTransparency = 0.9
    closeButton.Text = "X"
    closeButton.TextColor3 = TEXT_COLOR
    closeButton.Font = Enum.Font.GothamBold
    closeButton.TextSize = 18
    closeButton.BorderSizePixel = 0
    closeButton.Parent = header
    createCorner(closeButton, 8)

    closeButton.MouseEnter:Connect(function()
        tweenBackgroundColor(closeButton, Color3.fromRGB(237, 66, 69), 0.2)
    end)

    closeButton.MouseLeave:Connect(function()
        tweenBackgroundColor(closeButton, Color3.fromRGB(255, 255, 255), 0.2)
    end)

    closeButton.MouseButton1Click:Connect(function()
        isRunning = false
        gui:Destroy()
        print("[" .. os.date("%H:%M:%S") .. "] Auto-Joiner stopped by user")
    end)

    local content = Instance.new("Frame")
    content.Size = UDim2.new(1, -20, 1, -80)
    content.Position = UDim2.new(0, 10, 0, 70)
    content.BackgroundTransparency = 1
    content.Parent = mainFrame

    local infoCard = Instance.new("Frame")
    infoCard.Size = UDim2.new(1, 0, 0, 120)
    infoCard.BackgroundColor3 = SECONDARY_BG
    infoCard.BorderSizePixel = 0
    infoCard.Parent = content
    createCorner(infoCard, 10)

    local serverTitleLabel = Instance.new("TextLabel")
    serverTitleLabel.Size = UDim2.new(1, -20, 0, 20)
    serverTitleLabel.Position = UDim2.new(0, 10, 0, 10)
    serverTitleLabel.BackgroundTransparency = 1
    serverTitleLabel.Text = "CURRENT SERVER"
    serverTitleLabel.TextColor3 = TEXT_COLOR
    serverTitleLabel.Font = Enum.Font.GothamBold
    serverTitleLabel.TextSize = 11
    serverTitleLabel.TextXAlignment = Enum.TextXAlignment.Left
    serverTitleLabel.TextTransparency = 0.5
    serverTitleLabel.Parent = infoCard

    nameLabel = Instance.new("TextLabel")
    nameLabel.Size = UDim2.new(1, -20, 0, 20)
    nameLabel.Position = UDim2.new(0, 10, 0, 28)
    nameLabel.BackgroundTransparency = 1
    nameLabel.Text = "Waiting for data..."
    nameLabel.TextColor3 = TEXT_COLOR
    nameLabel.Font = Enum.Font.GothamBold
    nameLabel.TextSize = 14
    nameLabel.TextXAlignment = Enum.TextXAlignment.Left
    nameLabel.Parent = infoCard

    local moneyContainer = Instance.new("Frame")
    moneyContainer.Size = UDim2.new(1, -20, 0, 30)
    moneyContainer.Position = UDim2.new(0, 10, 0, 55)
    moneyContainer.BackgroundTransparency = 1
    moneyContainer.Parent = infoCard

    local moneyTitle = Instance.new("TextLabel")
    moneyTitle.Size = UDim2.new(0, 100, 1, 0)
    moneyTitle.BackgroundTransparency = 1
    moneyTitle.Text = "MONEY/SEC"
    moneyTitle.TextColor3 = TEXT_COLOR
    moneyTitle.Font = Enum.Font.GothamBold
    moneyTitle.TextSize = 11
    moneyTitle.TextXAlignment = Enum.TextXAlignment.Left
    moneyTitle.TextTransparency = 0.5
    moneyTitle.Parent = moneyContainer

    moneyLabel = Instance.new("TextLabel")
    moneyLabel.Size = UDim2.new(1, -110, 1, 0)
    moneyLabel.Position = UDim2.new(0, 110, 0, 0)
    moneyLabel.BackgroundTransparency = 1
    moneyLabel.Text = "0.0M/s"
    moneyLabel.TextColor3 = SUCCESS_COLOR
    moneyLabel.Font = Enum.Font.GothamBold
    moneyLabel.TextSize = 16
    moneyLabel.TextXAlignment = Enum.TextXAlignment.Right
    moneyLabel.Parent = moneyContainer

    local playersContainer = Instance.new("Frame")
    playersContainer.Size = UDim2.new(1, -20, 0, 30)
    playersContainer.Position = UDim2.new(0, 10, 0, 85)
    playersContainer.BackgroundTransparency = 1
    playersContainer.Parent = infoCard

    local playersTitle = Instance.new("TextLabel")
    playersTitle.Size = UDim2.new(0, 100, 1, 0)
    playersTitle.BackgroundTransparency = 1
    playersTitle.Text = "PLAYERS"
    playersTitle.TextColor3 = TEXT_COLOR
    playersTitle.Font = Enum.Font.GothamBold
    playersTitle.TextSize = 11
    playersTitle.TextXAlignment = Enum.TextXAlignment.Left
    playersTitle.TextTransparency = 0.5
    playersTitle.Parent = playersContainer

    playersLabel = Instance.new("TextLabel")
    playersLabel.Size = UDim2.new(1, -110, 1, 0)
    playersLabel.Position = UDim2.new(0, 110, 0, 0)
    playersLabel.BackgroundTransparency = 1
    playersLabel.Text = "0/0"
    playersLabel.TextColor3 = TEXT_COLOR
    playersLabel.Font = Enum.Font.Gotham
    playersLabel.TextSize = 13
    playersLabel.TextXAlignment = Enum.TextXAlignment.Right
    playersLabel.Parent = playersContainer

    autoJoinButton = Instance.new("TextButton")
    autoJoinButton.Size = UDim2.new(1, 0, 0, 45)
    autoJoinButton.Position = UDim2.new(0, 0, 0, 135)
    autoJoinButton.BackgroundColor3 = SUCCESS_COLOR
    autoJoinButton.Text = "AUTO-JOIN: ON"
    autoJoinButton.TextColor3 = TEXT_COLOR
    autoJoinButton.Font = Enum.Font.GothamBold
    autoJoinButton.TextSize = 14
    autoJoinButton.BorderSizePixel = 0
    autoJoinButton.Parent = content
    createCorner(autoJoinButton, 10)

    autoJoinButton.MouseButton1Click:Connect(function()
        autoJoinEnabled = not autoJoinEnabled
        if autoJoinEnabled then
            autoJoinButton.Text = "AUTO-JOIN: ON"
            tweenBackgroundColor(autoJoinButton, SUCCESS_COLOR, 0.2)
            log("Auto-join enabled", SUCCESS_COLOR)
        else
            autoJoinButton.Text = "AUTO-JOIN: OFF"
            tweenBackgroundColor(autoJoinButton, ERROR_COLOR, 0.2)
            log("Auto-join disabled", ERROR_COLOR)
        end
    end)

    local statusBar = Instance.new("Frame")
    statusBar.Size = UDim2.new(1, 0, 0, 40)
    statusBar.Position = UDim2.new(0, 0, 0, 195)
    statusBar.BackgroundColor3 = SECONDARY_BG
    statusBar.BorderSizePixel = 0
    statusBar.Parent = content
    createCorner(statusBar, 10)

    statusLabel = Instance.new("TextLabel")
    statusLabel.Size = UDim2.new(1, -20, 1, 0)
    statusLabel.Position = UDim2.new(0, 10, 0, 0)
    statusLabel.BackgroundTransparency = 1
    statusLabel.Text = "Connected to API!"
    statusLabel.TextColor3 = SUCCESS_COLOR
    statusLabel.Font = Enum.Font.Gotham
    statusLabel.TextSize = 12
    statusLabel.TextXAlignment = Enum.TextXAlignment.Left
    statusLabel.Parent = statusBar

    tweenSize(mainFrame, UDim2.new(0, 400, 0, 280), 0.5)

    log("GUI created successfully", SUCCESS_COLOR)
end

print("[" .. os.date("%H:%M:%S") .. "] Starting Roblox Auto-Joiner...")
print("[" .. os.date("%H:%M:%S") .. "] API URL: " .. API_URL)
print("[" .. os.date("%H:%M:%S") .. "] Player: " .. playerUsername)

createMainGUI()
task.wait(0.5)
startPolling()
