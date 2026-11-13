-- Val Jungle 40rd - UE4SS Lua, tape coupler concept
-- Patches BP_AS_Val_Mag_Med MaxStackSize 20->40 at runtime, no uasset crash
print("[ValJungleMag] Loading...")

-- Hook when mag is constructed
RegisterHook("/Game/ITR2/BPs/Items/Firearms/Primary/Val_and_VSS/BP_AS_Val_Mag_Med.BP_AS_Val_Mag_Med_C:UserConstructionScript", function(Context)
    -- Find BPC_ItemStackComponent on this mag
    local bpc = Context:getPropertyValue("BPC_ItemStackComponent")
    if bpc and bpc:IsValid() then
        local cur = bpc:getPropertyValue("MaxStackSize")
        if cur == 20 then
            bpc:setPropertyValue("MaxStackSize", 40)
            print("[ValJungleMag] Patched mag 20->40 on " .. Context:GetFullName())
        end
    end
end)

-- Also patch existing instances in world
RegisterHook("/Script/Engine.PlayerController:ClientRestart", function()
    print("[ValJungleMag] ClientRestart - scanning for mags")
    -- Find all mag instances and patch
    local mags = FindAllOf("BP_AS_Val_Mag_Med_C")
    if mags then
        for i, mag in ipairs(mags) do
            local bpc = mag:getPropertyValue("BPC_ItemStackComponent")
            if bpc and bpc:IsValid() then
                if bpc:getPropertyValue("MaxStackSize") == 20 then
                    bpc:setPropertyValue("MaxStackSize", 40)
                end
            end
        end
        print("[ValJungleMag] Patched " .. #mags .. " mags")
    end
end)

print("[ValJungleMag] Ready - tape coupler 2x20 as 40 (visual double mesh in pak)")
