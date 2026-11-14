-- {{NAME}} - Cyber Engine Tweaks entry point.
-- Events: onInit, onUpdate, onDraw, onOverlayOpen, onOverlayClose, onShutdown, onTweak
-- Log: this folder's {{ID}}.log; print() also goes to the CET console.

local mod = {
    ready = false,
    overlayOpen = false,
    enabled = true,
}

registerForEvent('onInit', function()
    mod.ready = true
    print('[{{ID}}] loaded')
end)

registerForEvent('onOverlayOpen', function()
    mod.overlayOpen = true
end)

registerForEvent('onOverlayClose', function()
    mod.overlayOpen = false
end)

-- Draw only while the CET overlay is open.
registerForEvent('onDraw', function()
    if not mod.overlayOpen then
        return
    end
    if ImGui.Begin('{{NAME}}') then
        mod.enabled = ImGui.Checkbox('Enabled', mod.enabled)
    end
    ImGui.End()
end)

-- Bind it in the CET overlay under Bindings.
registerHotkey('{{ID_LOWER}}_toggle', 'Toggle {{NAME}}', function()
    mod.enabled = not mod.enabled
    print('[{{ID}}] enabled = ' .. tostring(mod.enabled))
end)

return mod
